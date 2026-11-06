"""Build a deterministic, synthetic metadata package; never a measured truth."""
import argparse
import hashlib
import json
from pathlib import Path


def build(root, mutate=None, spatial=False):
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError('output directory must be absent or empty')
    root.mkdir(parents=True, exist_ok=True)
    records = []
    def write(name, document, **identity):
        if mutate:
            mutate(name, document)
        raw = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        (root / name).write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        records.append({'path': name, 'bytes': len(raw), 'sha256': digest,
                        'media_type': 'application/json'})
        return {'path': name, 'sha256': digest, **identity}
    scene = 'synthetic-equipment-corridor'
    truth_id = 'truth-spatial-sample-001' if spatial else 'truth-sample-001'
    release_id = 'release-spatial-sample-001' if spatial else 'release-sample-001'
    common = {'scene_id': scene, 'data_kind': 'synthetic'}
    frame = {'frame_id': 'sample-local', 'unit': 'm', 'handedness': 'right',
             'axes': ['along_corridor', 'left', 'up'],
             'origin_description': 'synthetic corridor entrance floor center'}
    ontology = write('ontology.json', {
        'ontology_id': 'sample-indoor', 'version': '0.1',
        'types': {kind: {'properties': {'name': {'type': 'string', 'required': True}}}
                  for kind in ('room', 'corridor', 'cabinet')}},
        ontology_id='sample-indoor', version='0.1')
    objects = write('objects.json', {'objects': [
        {'object_id': identity, 'type_id': kind, 'properties': {'name': name},
         'anchor_xyz': anchor, 'confirmation': 'synthetic'}
        for identity, kind, name, anchor in (
            ('room-a', 'room', '设备间A（合成）', [4, 3, 0]),
            ('corridor-a', 'corridor', '走廊A（合成）', [2, 0, 0]),
            ('cabinet-a', 'cabinet', '柜体A（合成）', [5, 3, 1]))]})
    coverage = None
    if spatial:
        coverage = write('coverage.json', {
            **common, 'frame_id': frame['frame_id'], 'bounds': [[0, -1, 0], [10, 6, 3]],
            'evidence': [{'evidence_id': 'synthetic-rays', 'kind': 'synthetic_observation',
                          'description': 'Hand-authored fixture, no sensor acquisition'}],
            'regions': [
                {'region_id': 'corridor-free', 'bounds': [[0, -1, 0], [4, 1, 2]],
                 'state': 'observed_free', 'reason': 'synthetic_observation', 'evidence_ids': ['synthetic-rays']},
                {'region_id': 'cabinet-occupied', 'bounds': [[4, 2, 0], [6, 4, 2]],
                 'state': 'occupied', 'reason': 'synthetic_observation', 'evidence_ids': ['synthetic-rays']},
                {'region_id': 'conflicting-return', 'bounds': [[3, 0, 0], [4, 1, 1]],
                 'state': 'occupied', 'reason': 'synthetic_observation', 'evidence_ids': ['synthetic-rays']} ]})
    truth = write('truth.json', {
        **common, 'truth_version_id': truth_id, 'parent_truth_version_id': None,
        'frame': frame, 'target_scope': [[0, -1, 0], [10, 6, 3]],
        'objects': objects, 'ontology_ref': ontology, 'adoption': 'sample_only',
        **({'coverage': coverage} if spatial else {}),
        'quality': {'status': 'not_field_validated',
                    'limitations': ['synthetic only; no measured geometry or coverage'] if spatial else ['metadata only; no measured geometry or coverage']},
        'provenance': {'method': 'scripts/build_sample.py; manual synthetic definitions'}},
        scene_id=scene, truth_version_id=truth_id)
    views = []
    for folder, kind in (('human', 'human'), ('agent', 'machine')):
        identity = folder + ('-spatial-sample-001' if spatial else '-sample-001')
        views.append(write(folder + '.json', {
            **common, 'view_version_id': identity, 'view_kind': kind,
            'source_truth': truth, 'frame': frame, 'objects': objects,
            'preparation': 'manual_sample',
            **({'coverage': coverage} if spatial else {}),
            'capabilities': ['reference_reading'] + (['synthetic_point_query'] if spatial and kind == 'machine' else []),
            'limitations': ['synthetic point queries only; no field quality, rendering, measurement or localization validation'] if spatial else ['no rendering, measurement, spatial query or localization validation']},
            view_version_id=identity))
    release = write('release.json', {
        **common, 'release_id': release_id, 'source_truth': truth,
        'views': views, 'capabilities': ['reference_reading'] + (['synthetic_point_query'] if spatial else [])})
    manifest = {'profile': 'cospace.synthetic-bundle/' + ('0.2' if spatial else '0.1'), **common,
                'release': release, 'data': {'files': records,
                    'source_description': 'Hand-authored synthetic identities and coordinates; no acquisition'}}
    if mutate:
        mutate('package.json', manifest)
    (root / 'package.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    parser.add_argument('--spatial', action='store_true')
    args = parser.parse_args()
    build(args.output, spatial=args.spatial)
