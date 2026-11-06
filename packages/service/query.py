"""Pinned, validated in-memory snapshot of a local synthetic package."""
from copy import deepcopy
from itertools import product
from math import prod
import hashlib
from packages.data.inventory import inventory
from packages.data.structure import check_structure
from packages.ontology.validation import inspect_instances
from packages.service.sample import inspect_package, read_json
from packages.spatial.coverage import query_coverage


class QueryError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class SampleService:
    def __init__(self, root):
        self._report, self._snapshot = inspect_package(root)
        if self._snapshot['coverage'] is None:
            raise QueryError('capability_unavailable', 'sample profile has no point-query capability')

    def export_snapshot(self):
        return deepcopy({'report': self._report, 'snapshot': self._snapshot})

    @classmethod
    def from_snapshot(cls, payload):
        service = cls.__new__(cls)
        service._report = deepcopy(payload['report'])
        service._snapshot = deepcopy(payload['snapshot'])
        return service

    def describe(self):
        return deepcopy({**self._report, 'frame_id': self._snapshot['truth']['frame']['frame_id'],
                'package_sha256': self._snapshot['package_sha256'],
                'release_sha256': self._snapshot['release_sha256']})

    def inspection(self, kind):
        audit = self._snapshot.get('inspection')
        if audit is None:
            raise QueryError('inspection_unavailable', 'legacy snapshot has no inspection payload; register a new release')
        try:
            if audit['version'] != 1:
                raise ValueError('unsupported inspection snapshot')
            raw = audit['manifest_raw'].encode('utf-8')
            if hashlib.sha256(raw).hexdigest() != self._snapshot['package_sha256']:
                raise ValueError('manifest digest mismatch')
            manifest = read_json(raw)
            check_structure(manifest, 'package', 'package.json', self._report['profile'])
            if kind == 'data':
                content = inventory(manifest, audit['roles'])
            elif kind == 'ontology':
                ref = self._snapshot['truth']['ontology_ref']
                raw = audit['ontology_raw'].encode('utf-8')
                record = next(r for r in manifest['data']['files'] if r['path'] == ref['path'])
                if (hashlib.sha256(raw).hexdigest() != ref['sha256'] or record['sha256'] != ref['sha256']
                        or len(raw) != record['bytes']):
                    raise ValueError('ontology digest mismatch')
                definition = read_json(raw)
                check_structure(definition, 'ontology', ref['path'], self._report['profile'])
                if definition['ontology_id'] != ref['ontology_id'] or definition['version'] != ref['version']:
                    raise ValueError('ontology identity mismatch')
                content = {**inspect_instances(definition, self._snapshot['objects']),
                           'ontology_sha256': ref['sha256']}
            else:
                raise ValueError('unsupported inspection kind')
            return {**self.describe(), **content}
        except (ValueError, KeyError, TypeError, StopIteration) as error:
            raise QueryError('content_corrupt', f'fixed inspection content invalid: {error}') from error

    def query(self, scene_id, release_id, frame_id, point):
        if scene_id != self._report['scene_id'] or release_id != self._report['release_id']:
            raise QueryError('version_mismatch', 'request does not match loaded scene/release')
        if frame_id != self._snapshot['truth']['frame']['frame_id']:
            raise QueryError('frame_mismatch', 'request coordinate frame differs from loaded truth')
        result = query_coverage(self._snapshot['coverage'], point)
        return {**self.describe(), 'point': list(point), **result}

    def human(self):
        """Bounded synthetic preview; exact partition uses the point-query policy."""
        if 'human_view' not in self._snapshot or 'objects' not in self._snapshot:
            raise QueryError('human_view_unavailable', 'legacy snapshot has no human payload; register a new release')
        coverage = self._snapshot['coverage']
        axes = [sorted({corner[i] for box in [coverage['bounds']] +
                        [r['bounds'] for r in coverage['regions']] for corner in box}) for i in range(3)]
        if prod(len(axis) - 1 for axis in axes) > 4096:
            raise QueryError('preview_too_complex', 'synthetic preview exceeds 4096 cells; tiled view required')
        cells = []
        for intervals in product(*(list(zip(axis, axis[1:])) for axis in axes)):
            bounds = [list(corner) for corner in zip(*intervals)]
            result = query_coverage(coverage, [a / 2 + b / 2 for a, b in intervals])
            cells.append({'bounds': bounds, **result})
        return deepcopy({**self.describe(), 'view_version_id': self._snapshot['human_view']['view_version_id'],
                         'representation': 'synthetic_cells_v0.1', 'frame': self._snapshot['truth']['frame'],
                         'bounds': coverage['bounds'], 'objects': self._snapshot['objects'], 'cells': cells,
                         'evidence': coverage['evidence']})
