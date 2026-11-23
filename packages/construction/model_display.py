"""Rebuildable Potree display derivatives, separate from immutable model publications."""
from contextlib import asynccontextmanager
import asyncio
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading

import numpy as np

from packages.construction.preview_model import PreviewModel, digest
from packages.lifecycle.preview_scope import scope, match, owned

PROFILE = 'cospace.model-display/0.1'
CONVERTER = 'potree-converter/2.1.5'
PROVIDER = 'potree/1.8.2'
AGENT_SOURCE = 'agent.npz'
BLOCK_BYTES = 256 * 1024
MAX_RANGE = 16 * 1024 * 1024
FILES = {'metadata.json', 'hierarchy.bin', 'octree.bin'}
STRATEGIES = {'baseline', 'task', 'adaptive', 'governance', 'combined'}
LOG = logging.getLogger(__name__)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def small_json(path, budget=2 * 1024 * 1024):
    with path.open('rb') as stream:
        raw = stream.read(budget + 1)
    if len(raw) > budget:
        raise ValueError('display_manifest_budget')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('display_manifest_invalid')
    return value, raw


def identity(manifest_raw):
    return sha256(encoded({'manifest': sha256(manifest_raw).hexdigest(),
                           'converter': CONVERTER, 'encoding': 'UNCOMPRESSED',
                           'scale_m': 0.00001, 'basis': 'z-up/1', 'revision': 2, 'profile': PROFILE})).hexdigest()


def agent_identity(manifest_raw):
    return sha256(encoded({'visual_id': identity(manifest_raw), 'view': 'agent', 'revision': 1})).hexdigest()


def surface_centers(root, model):
    source = model['agent_view']
    path = root / AGENT_SOURCE
    if source.get('path') != AGENT_SOURCE or digest(path) != model['members'][AGENT_SOURCE]['sha256']:
        raise ValueError('agent_display_source_changed')
    with np.load(path, allow_pickle=False) as data:
        cells = data['cells']
    resolution = source['resolution_m']
    if (cells.dtype.kind not in 'iu' or cells.shape != (source['surface_cells'], 3)
            or not np.isfinite(resolution) or resolution <= 0 or len(np.unique(cells, axis=0)) != len(cells)):
        raise ValueError('agent_display_cells_invalid')
    return (cells.astype(np.float64) + .5) * resolution


def byte_range(header, size):
    """One bounded HTTP byte range; never accidentally return the full octree."""
    if header and len(header) > 128:
        raise ValueError('display_range_invalid')
    found = re.fullmatch(r'bytes=(\d*)-(\d*)', header or '')
    if not found or not any(found.groups()) or size <= 0:
        raise ValueError('display_range_invalid')
    left, right = found.groups()
    if not left:
        count = int(right)
        if count <= 0:
            raise ValueError('display_range_invalid')
        start, end = max(0, size - count), size - 1
    else:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
    if start >= size or start > end or end - start + 1 > MAX_RANGE:
        raise ValueError('display_range_invalid')
    return start, end


class ModelDisplays:
    def __init__(self, jobs, converter=None, strategy=None):
        self.jobs = jobs
        self.root = jobs.root.parent / 'model-displays'
        self.converter = converter or os.environ.get('COSPACE_POTREE_CONVERTER')
        configured = strategy if strategy is not None else os.environ.get('COSPACE_DISPLAY_STRATEGY', 'baseline')
        self.strategy = configured if configured in STRATEGIES else 'baseline'
        if configured not in STRATEGIES:
            LOG.warning('Unknown display strategy; using mature baseline')
        self.lock = threading.Lock()
        self.read_slots = threading.BoundedSemaphore(8)
        self.stopping = threading.Event()
        self.process = None
        from packages.construction.model_exact import ModelExact
        self.exact = ModelExact(self)

    def source(self, kind, name):
        """Resolve only small saved records; the HTTP gate authorizes their scene first."""
        if kind == 'candidate' and re.fullmatch(r'build-[A-Za-z0-9-]+', name):
            folder = self.jobs.root / name
            record, _ = small_json(folder / 'job.json')
            if record.get('id') != name or record.get('state') != 'succeeded':
                raise ValueError('display_candidate_not_ready')
            model_root = folder / 'output'
        elif kind == 'publication' and re.fullmatch(r'preview-[a-f0-9]{16}', name):
            model_root = self.jobs.root / 'publications' / name
            record, _ = small_json(model_root / 'publication.json')
            if record.get('id') != name:
                raise ValueError('display_publication_invalid')
        else:
            raise ValueError('display_source_invalid')
        manifest, raw = small_json(model_root / 'model.json')
        ownership = scope(self.jobs.directory, record.get('space_id'))
        match(record, ownership)
        match(manifest, ownership)
        canonical = manifest['members']['spatial.npz']['sha256']
        if manifest.get('profile') != 'cospace.real-model-preview/0.1':
            raise ValueError('display_model_invalid')
        if kind == 'publication':
            if (record.get('model_manifest_sha256') != sha256(raw).hexdigest()
                    or record.get('candidate_id') != manifest.get('id')
                    or record.get('source_model_sha256') != canonical
                    or record.get('derivation') != manifest.get('derivation')):
                raise ValueError('display_publication_binding')
        else:
            if (manifest.get('id') != name
                    or record.get('input_binding') is not None and record['input_binding'] != manifest.get('source', {}).get('input_binding')
                    or record.get('batch_ref') != manifest.get('source', {}).get('batch_ref')):
                raise ValueError('display_candidate_binding')
            if ownership:
                match(manifest.get('source', {}).get('input_binding', {}), ownership)
            from packages.construction.build_admission import match_source
            match_source(record, manifest.get('source', {}))
            if record.get('pipeline') == 'model_then_views/0.1':
                declaration = manifest.get('derivation', {})
                if (declaration.get('frozen_model') != record.get('frozen_model')
                        or any(declaration.get('views', {}).get(view, {}).get('id') != ref['task_id']
                               for view, ref in record.get('view_tasks', {}).items())):
                    raise ValueError('display_view_task_binding')
        for view in ('human_view', 'agent_view'):
            if manifest.get(view, {}).get('source_model_sha256') != canonical:
                raise ValueError('display_view_binding')
        return model_root, record, manifest, raw

    def _describe_display(self, kind, name, model, raw, *, agent=False):
        key = agent_identity(raw) if agent else identity(raw)
        path = self.root / key / 'display.json'
        result = {'profile': PROFILE, 'id': key, 'provider': PROVIDER,
                  'source_manifest_sha256': sha256(raw).hexdigest(),
                  'source_model_sha256': model['members']['spatial.npz']['sha256']}
        if agent:
            source = model['agent_view']
            result.update(view='agent', source_agent_sha256=model['members'][AGENT_SOURCE]['sha256'],
                          resolution_m=source['resolution_m'])
            if source['surface_cells'] == 0:
                return result | {'state': 'empty', 'point_count': 0}
        if path.is_file():
            saved, _ = small_json(path, 8 * 1024 * 1024)
            if any(saved.get(k) != v for k, v in result.items()):
                raise ValueError('display_binding_changed')
            if agent and saved.get('point_count') != model['agent_view']['surface_cells']:
                raise ValueError('agent_display_count_changed')
            if saved.get('block_bytes') != BLOCK_BYTES or set(saved.get('files', {})) != FILES:
                raise ValueError('display_integrity_index_invalid')
            for info in saved['files'].values():
                size = info['bytes']
                if (type(size) is not int or size <= 0 or not re.fullmatch('[a-f0-9]{64}', info['sha256'])
                        or len(info['blocks']) != (size + BLOCK_BYTES - 1) // BLOCK_BYTES):
                    raise ValueError('display_integrity_index_invalid')
            result = saved | {'state': 'ready', 'entry': f'/{"publications" if kind == "publication" else "candidates"}/{name}/display/{key}/metadata.json'}
        else:
            failure = self.root / (key + '.error.json')
            result['state'] = 'failed' if failure.exists() else 'preparing' if self.converter else 'unavailable'
        return result

    def describe(self, kind, name):
        _, record, model, raw = self.source(kind, name)
        result = self._describe_display(kind, name, model, raw)
        output = {'display': result | {'strategy': self.strategy}}
        if 'surface_cells' in model['agent_view']:
            try:
                output['agent_display'] = self._describe_display(kind, name, model, raw, agent=True)
            except (ValueError, OSError, LookupError, TypeError, AttributeError):
                # Damage to the optional derivative must not prevent visual browsing.
                LOG.warning('Agent display descriptor invalid: %s', agent_identity(raw))
                output['agent_display'] = self._agent_failed(model, raw)
        if kind == 'publication':
            model = model | {'publication': record}
        return output | {'model': model}

    @staticmethod
    def _agent_failed(model, raw):
        return {'profile': PROFILE, 'id': agent_identity(raw), 'provider': PROVIDER, 'view': 'agent',
                'source_manifest_sha256': sha256(raw).hexdigest(), 'state': 'failed',
                'source_model_sha256': model['members']['spatial.npz']['sha256'],
                'source_agent_sha256': model.get('members', {}).get(AGENT_SOURCE, {}).get('sha256'),
                'resolution_m': model['agent_view'].get('resolution_m')}

    def build(self, kind, name, *, agent=False):
        if not self.converter:
            return
        model_root, _, manifest, raw = self.source(kind, name)
        key = agent_identity(raw) if agent else identity(raw)
        if agent and not manifest['agent_view'].get('surface_cells'):
            return
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock:
            destination = self.root / key
            if destination.is_dir():
                return
            with tempfile.TemporaryDirectory(prefix='.display-', dir=self.root) as staging:
                staging = Path(staging)
                import laspy
                if agent:
                    visual = self._describe_display(kind, name, manifest, raw)
                    if visual['state'] != 'ready':
                        return
                    points = surface_centers(model_root, manifest)
                    colors = np.broadcast_to(np.array([96, 213, 237], dtype=np.uint8), points.shape)
                    origin, basis = np.array(visual['origin_m']), np.array(visual['model_to_display'])
                else:
                    # Full source checks are reserved for offline generation.
                    PreviewModel(model_root)
                    with np.load(model_root / 'spatial.npz', allow_pickle=False) as data:
                        points, colors = data['points'], data['colors']
                    origin = (points.min(axis=0).astype(float) + points.max(axis=0).astype(float)) / 2
                    basis = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]] if manifest.get('axes') == ['right', 'down', 'forward'] else np.eye(3))
                if (points.ndim != 2 or points.shape[1] != 3 or not len(points)
                        or points.shape != colors.shape or not np.isfinite(points).all()
                        or not np.isfinite(colors).all() or np.any(colors < 0) or np.any(colors > 255)):
                    raise ValueError('display_geometry_invalid')
                header = laspy.LasHeader(point_format=2, version='1.2')
                header.scales = np.full(3, 0.00001)
                local = (points.astype(np.float64) - origin) @ basis.T
                header.offsets = local.min(axis=0)
                if np.any(np.ptp(local, axis=0) / header.scales >= 2**31 - 1):
                    raise ValueError('display_coordinate_extent')
                cloud = laspy.LasData(header)
                cloud.x, cloud.y, cloud.z = local.T
                cloud.red, cloud.green, cloud.blue = (colors.astype(np.uint16) * 257).T
                cloud.write(staging / 'source.las')
                restored = np.column_stack((cloud.x, cloud.y, cloud.z)) @ basis + origin
                error = float(np.max(np.abs(restored - points)))
                # Include intermediate float32 arithmetic in the native converter/renderer.
                # This is a conservative bound, not just the LAS rounding measurement.
                error_bound = error + float(np.ptp(local, axis=0).max()) * float(np.finfo(np.float32).eps) * 4 + 0.00002
                if error_bound > 0.001:
                    raise ValueError('display_coordinate_error')
                output = staging / 'output'
                command = [str(self.converter), str(staging / 'source.las'), '-o', str(output),
                           '--encoding', 'UNCOMPRESSED', '--attributes', 'rgb']
                if self.stopping.is_set():
                    raise ValueError('display_generation_interrupted')
                with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
                    self.process = process
                    try:
                        process.communicate(timeout=600)
                        if process.returncode:
                            raise ValueError('display_converter_failed')
                    except BaseException:
                        process.kill()
                        process.communicate()
                        raise
                    finally:
                        self.process = None
                metadata = json.loads((output / 'metadata.json').read_bytes())
                if metadata.get('points') != len(points) or metadata.get('encoding') != 'UNCOMPRESSED':
                    raise ValueError('display_conversion_invalid')
                files = {}
                for member in FILES:
                    path = output / member
                    blocks = []
                    with path.open('rb') as stream:
                        while block := stream.read(BLOCK_BYTES):
                            blocks.append(sha256(block).hexdigest())
                    files[member] = {'bytes': path.stat().st_size, 'sha256': digest(path), 'blocks': blocks}
                info = {'profile': PROFILE, 'id': key, 'provider': PROVIDER,
                        'source_manifest_sha256': sha256(raw).hexdigest(),
                        'source_model_sha256': manifest['members']['spatial.npz']['sha256'],
                        'converter': CONVERTER, 'origin_m': origin.tolist(), 'model_to_display': basis.tolist(), 'point_count': len(points),
                        'encoding_error_m': error_bound, 'las_roundtrip_error_m': error,
                        'error_estimation': 'conservative_local_float32_bound', 'block_bytes': BLOCK_BYTES, 'files': files}
                if agent:
                    info.update(view='agent', source_agent_sha256=manifest['members'][AGENT_SOURCE]['sha256'],
                                resolution_m=manifest['agent_view']['resolution_m'], sample_m=points[0].tolist())
                if (model_root / 'model.json').read_bytes() != raw:
                    raise ValueError('display_source_changed')
                (output / 'display.json').write_bytes(encoded(info))
                output.rename(destination)
                (self.root / (key + '.error.json')).unlink(missing_ok=True)

    def resource(self, kind, name, key, member, header=None):
        if member not in FILES or not re.fullmatch('[a-f0-9]{64}', key):
            raise ValueError('display_resource_invalid')
        described = self.resource_display(kind, name, key)
        if described['state'] != 'ready' or described['id'] != key:
            raise ValueError('display_version_changed')
        info = described['files'][member]
        size = info['bytes']
        if header:
            start, end = byte_range(header, size)
        elif member == 'metadata.json' and size <= 50 * 1024:
            start, end = 0, size - 1
        else:
            raise ValueError('display_range_required')
        first, last = start // BLOCK_BYTES, end // BLOCK_BYTES
        with self.read_slots, (self.root / key / member).open('rb') as stream:
            if os.fstat(stream.fileno()).st_size != size:
                raise ValueError('display_integrity_changed')
            stream.seek(first * BLOCK_BYTES)
            chunks = []
            for index in range(first, last + 1):
                block = stream.read(BLOCK_BYTES)
                if sha256(block).hexdigest() != info['blocks'][index]:
                    raise ValueError('display_integrity_changed')
                chunks.append(block)
        raw = b''.join(chunks)
        offset = start - first * BLOCK_BYTES
        return raw[offset:offset + end - start + 1], start, end, size, info['sha256']

    def resource_display(self, kind, name, key):
        _, _, model, raw = self.source(kind, name)
        if key == identity(raw):
            return self._describe_display(kind, name, model, raw)
        if key == agent_identity(raw) and 'surface_cells' in model['agent_view']:
            return self._describe_display(kind, name, model, raw, agent=True)
        raise ValueError('display_version_changed')

    def scan(self):
        if not self.converter:
            return
        sources = [('candidate', p.parent.name) for p in self.jobs.root.glob('*/job.json')]
        sources += [('publication', p.parent.name) for p in (self.jobs.root / 'publications').glob('*/publication.json')]
        # Keep visual backfill ahead of optional computation backfill.
        for agent in (False, True):
            self._scan(sources, agent)

    def _scan(self, sources, agent):
        for kind, name in sources:
            if self.stopping.is_set():
                return
            key = None
            try:
                _, _, _, raw = self.source(kind, name)
                key = agent_identity(raw) if agent else identity(raw)
                if (self.root / (key + '.error.json')).exists():
                    continue
                self.build(kind, name, agent=agent)
            except (ValueError, OSError, LookupError, TypeError, AttributeError, subprocess.SubprocessError, ImportError):
                if key and not self.stopping.is_set():
                    LOG.warning('Display derivative generation failed: %s', key)
                    try:
                        self.root.mkdir(parents=True, exist_ok=True)
                        (self.root / (key + '.error.json')).write_bytes(encoded({'error': 'display_generation_failed'}))
                    except OSError:
                        LOG.warning('Display failure state could not be persisted: %s', key)

    @asynccontextmanager
    async def lifespan(self, app):
        self.stopping.clear()
        async def run():
            while not self.stopping.is_set():
                await asyncio.to_thread(self.scan)
                await asyncio.sleep(5)
        async def exact_run():
            while not self.stopping.is_set():
                await asyncio.to_thread(self.exact.scan)
                await asyncio.sleep(1)
        tasks = [asyncio.create_task(run()), asyncio.create_task(exact_run())]
        try:
            yield
        finally:
            self.stopping.set()
            self.exact.clear()
            if self.process is not None:
                try:
                    self.process.kill()
                except OSError:
                    pass
            try:
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=15)
            except (asyncio.CancelledError, TimeoutError):
                pass
