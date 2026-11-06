"""Offline sample consistency check; does not authorize a real release."""
import json
import hashlib
from pathlib import Path

from packages.data.validation import verify_files
from packages.data.structure import check_structure
from packages.ontology.validation import validate_instances
from packages.spatial.validation import validate_spatial
from packages.spatial.coverage import validate_coverage


def read_json(raw):
    def reject_constant(value):
        raise ValueError(f'nonfinite JSON number: {value}')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_pairs)


def inspect_package(root, channel='sample'):
    if channel != 'sample':
        raise ValueError('real release validation is not implemented; sample channel only')
    root = Path(root)
    manifest_raw = (root / 'package.json').read_bytes()
    manifest = read_json(manifest_raw)
    if not isinstance(manifest, dict):
        check_structure(manifest, 'package', 'package.json')
    profile = manifest.get('profile', 'cospace.synthetic-bundle/0.1')
    if profile not in ('cospace.synthetic-bundle/0.1', 'cospace.synthetic-bundle/0.2'):
        raise ValueError('unsupported sample profile version')
    check_structure(manifest, 'package', 'package.json', profile)
    spatial = profile.endswith('/0.2')
    if manifest['data_kind'] != 'synthetic':
        raise ValueError('profile is restricted to synthetic data')
    scene = manifest['scene_id']
    if not isinstance(scene, str) or not scene:
        raise ValueError('scene_id must be nonempty')
    files = verify_files(root, manifest['data']['files'])
    if not manifest['data']['source_description']:
        raise ValueError('sample source description required')
    roles = {}
    def load(reference, definition):
        name = reference['path']
        if name not in files:
            raise ValueError(f'unregistered artifact: {name}')
        record = next(r for r in manifest['data']['files'] if r['path'] == name)
        if reference['sha256'] != record['sha256']:
            raise ValueError(f'reference digest mismatch: {name}')
        document = read_json(files[name])
        check_structure(document, definition, name, profile)
        roles[name] = definition if definition != 'view' else f"{document['view_kind']}_view"
        return document
    def identity(document, field):
        if document['scene_id'] != scene or document['data_kind'] != 'synthetic':
            raise ValueError('scene or data-kind mismatch')
        if not isinstance(document[field], str) or not document[field]:
            raise ValueError(f'invalid identity: {field}')
    release = load(manifest['release'], 'release')
    identity(release, 'release_id')
    truth_ref = release['source_truth']
    truth = load(truth_ref, 'truth')
    identity(truth, 'truth_version_id')
    expected_source = dict(truth_ref)
    if truth_ref['truth_version_id'] != truth['truth_version_id'] or truth_ref['scene_id'] != scene:
        raise ValueError('truth identity mismatch')
    if truth['adoption'] != 'sample_only' or truth['quality']['status'] != 'not_field_validated':
        raise ValueError('sample must not claim real adoption or field quality')
    ontology_ref = truth['ontology_ref']
    ontology = load(ontology_ref, 'ontology')
    if (ontology_ref['ontology_id'] != ontology['ontology_id']
            or ontology_ref['version'] != ontology['version']):
        raise ValueError('ontology identity/version mismatch')
    objects = load(truth['objects'], 'objects')['objects']
    if not objects:
        raise ValueError('sample must include semantic objects')
    validate_instances(ontology, objects)
    validate_spatial(truth, objects)
    coverage = load(truth['coverage'], 'coverage') if spatial else None
    if spatial:
        validate_coverage(coverage, truth)
    kinds, view_ids = set(), set()
    human_view = None
    for reference in release['views']:
        view = load(reference, 'view')
        identity(view, 'view_version_id')
        if reference['view_version_id'] != view['view_version_id']:
            raise ValueError('view identity mismatch')
        if view['view_version_id'] in view_ids:
            raise ValueError('duplicate view identity')
        view_ids.add(view['view_version_id'])
        kinds.add(view['view_kind'])
        if view['view_kind'] == 'human':
            human_view = view
        if view['source_truth'] != expected_source:
            raise ValueError('view uses a different truth source')
        if view['frame'] != truth['frame']:
            raise ValueError('view coordinate definition differs from truth')
        if view['preparation'] != 'manual_sample':
            raise ValueError('unsupported sample preparation')
        expected = ['reference_reading'] + (['synthetic_point_query'] if spatial and view['view_kind'] == 'machine' else [])
        if view['capabilities'] != expected:
            raise ValueError('profile only checks reference reading, not spatial or localization capability')
        if spatial and view['coverage'] != truth['coverage']:
            raise ValueError('view coverage source differs from truth')
        load(view['objects'], 'objects')
        if view['objects'] != truth['objects']:
            raise ValueError('sample views must preserve the fixed object snapshot')
    if kinds != {'human', 'machine'}:
        raise ValueError('sample requires human and machine views')
    if release['capabilities'] != ['reference_reading'] + (['synthetic_point_query'] if spatial else []):
        raise ValueError('release capability is outside validated sample profile')
    report = {'passed': True, 'profile': manifest['profile'], 'scene_id': scene,
            'release_id': release['release_id'], 'truth_version_id': truth['truth_version_id'],
            'views': sorted(view_ids), 'ontology_id': ontology['ontology_id'],
            'ontology_version': ontology['version'], 'verified_files': len(files),
            'data_kind': 'synthetic', 'real_release_ready': False,
            'scope': 'synthetic point queries and metadata consistency' if spatial else 'offline reference, identity, coordinate and basic type consistency only'}
    return report, {'truth': truth, 'release': release, 'coverage': coverage,
                    'objects': objects, 'human_view': human_view,
                    'inspection': {'version': 1, 'manifest_raw': manifest_raw.decode('utf-8'),
                                   'ontology_raw': files[ontology_ref['path']].decode('utf-8'),
                                   'roles': roles},
                    'package_sha256': hashlib.sha256(manifest_raw).hexdigest(),
                    'release_sha256': manifest['release']['sha256']}


def validate_package(root, channel='sample'):
    return inspect_package(root, channel)[0]
