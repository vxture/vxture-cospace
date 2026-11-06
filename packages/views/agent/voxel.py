"""F05 synthetic u8 chunks; local point-state experiment, no validity authority."""
import copy
import hashlib
import json
import math
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from packages.service.sample import read_json
from packages.service.release_contract import inspect_release_snapshot

SCHEMA = Path(__file__).resolve().parents[3] / 'contracts/schemas/agent-voxel-v0.1.schema.json'
SUPPORTED = ('occupancy', 'cospace.occupancy-u8/0.1')
STATES = {
    0: ('unknown', 'unobserved'), 1: ('observed_free', 'synthetic_observation'),
    2: ('occupied', 'synthetic_observation'), 3: ('unknown', 'degraded'),
    4: ('unknown', 'conflict')}


def finite_number(value):
    if type(value) not in (int,float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def pinned_voxel_source(snapshot, *, now):
    """Extract a pin only after F04 consistency validation; not a trusted signature."""
    report = inspect_release_snapshot(snapshot, now=now)
    release = read_json(snapshot['release.json'])
    views = [r for r in release['views'] if read_json(snapshot[r['path']])['view_kind'] == 'machine']
    if len(views) != 1:
        raise ValueError('select_exactly_one_machine_view')
    view = views[0]
    truth = read_json(snapshot[release['source_truth']['path']])
    scope = read_json(snapshot[truth['scope']['path']])
    return {
        'source': {'scene_id':release['scene_id'],'release_id':release['id'],
                   'release_sha256':report['release_sha256'],'truth_id':truth['id'],
                   'truth_sha256':release['source_truth']['sha256'],'view_id':view['id'],'view_sha256':view['sha256']},
        'frame_id':truth['frame']['id'],'bounds':scope['bounds']}


class VoxelSession:
    """Immutable bounded resident chunks. Unlisted chunks are unknown, never free."""
    def __init__(self, files, expected_source):
        if not isinstance(files, dict) or len(files) > 4097:
            raise ValueError('invalid_member_catalog')
        snapshot = dict(files)
        paths = set()
        for path, raw in snapshot.items():
            if (not isinstance(path,str) or not path or '\\' in path or re.search(r'[:\x00-\x1f]',path)
                    or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in path.split('/'))):
                raise ValueError('unsafe_member_path')
            if path.casefold() in paths:
                raise ValueError('duplicate_member_path')
            paths.add(path.casefold())
            if type(raw) is not bytes or len(raw) > 8388608:
                raise ValueError('invalid_member_bytes')
        self.package_bytes = sum(len(raw) for raw in snapshot.values())
        if self.package_bytes > 33554432 or 'agent-voxel.json' not in snapshot:
            raise ValueError('package_budget_or_manifest')
        raw = snapshot['agent-voxel.json']
        m = read_json(raw)
        schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
        if list(Draft202012Validator(schema).iter_errors(m)):
            raise ValueError('manifest_structure')
        self.manifest_sha256 = hashlib.sha256(raw).hexdigest()
        if m['source'] != expected_source['source'] or m['frame_id'] != expected_source['frame_id']:
            raise ValueError('source_binding_mismatch')
        if not all(finite_number(x) for x in [*m['origin_m'], m['resolution_m']]):
            raise ValueError('nonfinite_grid')
        if any(type(x) is not int for x in m['dimensions'] + m['chunk_shape']):
            raise ValueError('literal_grid_integer_required')
        if math.prod(m['dimensions']) > 10000000 or math.prod(m['chunk_shape']) > 8388608:
            raise ValueError('grid_budget')
        if any(d % c for d,c in zip(m['dimensions'],m['chunk_shape'])):
            raise ValueError('grid_not_chunk_aligned')
        upper = [o + d*m['resolution_m'] for o,d in zip(m['origin_m'],m['dimensions'])]
        if not all(math.isfinite(x) for x in upper):
            raise ValueError('nonfinite_grid_extent')
        if any(u <= o for o,u in zip(m['origin_m'],upper)):
            raise ValueError('unrepresentable_grid_extent')
        bounds = expected_source['bounds']
        if m['origin_m'] != bounds[0] or upper != bounds[1]:
            raise ValueError('source_scope_mismatch')
        ids = [c['id'] for c in m['components']]
        if len(set(ids)) != len(ids):
            raise ValueError('duplicate_component')
        components = {c['id']:c for c in m['components']}
        supported, skipped = set(), []
        for component in components.values():
            if (component['role'],component['encoding']) == SUPPORTED:
                supported.add(component['id'])
                if not component['required']:
                    raise ValueError('occupancy_must_be_required')
            elif component['required']:
                raise ValueError('unsupported_required_component')
            else:
                skipped.append(component['id'])
            if set(component['depends_on']) - components.keys():
                raise ValueError('missing_component_dependency')
        if len(supported) != 1:
            raise ValueError('exactly_one_occupancy_required')
        visited, active = set(), set()
        def visit(identity):
            if identity in active:
                raise ValueError('component_dependency_cycle')
            if identity in visited:
                return
            active.add(identity)
            for dep in components[identity]['depends_on']:
                visit(dep)
            active.remove(identity)
            visited.add(identity)
        for identity in components:
            visit(identity)
        for identity in supported:
            if set(components[identity]['depends_on']) - supported:
                raise ValueError('unsupported_component_dependency')
        chunks, used = {}, {'agent-voxel.json'}
        for chunk in m['chunks']:
            index, ref = chunk['index'],chunk['member']
            if any(type(i) is not int for i in index):
                raise ValueError('literal_chunk_index_required')
            key = tuple(index)
            if key in chunks or any(i >= d//c for i,d,c in zip(index,m['dimensions'],m['chunk_shape'])):
                raise ValueError('duplicate_or_outside_chunk')
            path = ref['path']
            if path in used:
                raise ValueError('duplicate_chunk_member')
            if path not in snapshot:
                raise ValueError('listed_chunk_missing')
            payload = snapshot[path]
            if (type(ref['bytes']) is not int or ref['bytes'] != math.prod(m['chunk_shape'])
                    or len(payload) != ref['bytes'] or hashlib.sha256(payload).hexdigest() != ref['sha256']):
                raise ValueError('chunk_integrity_mismatch')
            if any(value not in STATES for value in payload):
                raise ValueError('unsupported_voxel_code')
            chunks[key] = payload
            used.add(path)
        if set(snapshot) != used:
            raise ValueError('unreferenced_members')
        self._manifest = m
        self._chunks = chunks
        self.skipped_components = tuple(skipped)
        self.loaded_chunk_bytes = sum(map(len,chunks.values()))

    def query(self, point):
        if (not isinstance(point,(list,tuple)) or len(point)!=3 or
                any(not finite_number(x) for x in point)):
            raise ValueError('point_requires_three_finite_numbers')
        m = self._manifest
        upper = [o + d*m['resolution_m'] for o,d in zip(m['origin_m'],m['dimensions'])]
        if any(not o <= p < u for o,p,u in zip(m['origin_m'],point,upper)):
            state,reason = 'out_of_scope','outside_target_scope'
        else:
            cell = [math.floor((p-o)/m['resolution_m']) for p,o in zip(point,m['origin_m'])]
            # Clamp only floating division roundoff after the half-open bounds check.
            cell = [min(i,d-1) for i,d in zip(cell,m['dimensions'])]
            key = tuple(i//c for i,c in zip(cell,m['chunk_shape']))
            payload = self._chunks.get(key)
            if payload is None:
                state,reason = 'unknown','missing_chunk'
            else:
                x,y,z = [i%c for i,c in zip(cell,m['chunk_shape'])]
                nx,ny,_ = m['chunk_shape']
                state,reason = STATES[payload[x+nx*(y+ny*z)]]
        return {'state':state,'reason':reason,'source':copy.deepcopy(m['source']),
                'package_sha256':self.manifest_sha256,'robot_ready':False,
                'authorized':False,'source_geometry_consistency_verified':False,
                'validity':'synthetic_unverified_only'}
