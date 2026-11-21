"""Immutable approved registration closure shared by online and offline readers."""
from hashlib import sha256
import json
import re

from packages.service.scene_registrations import Snapshot, require, instant
from packages.spatial.georeference import evaluate_registration
from packages.spatial.registration_geography import validate_binding, project_objects
from packages.spatial.scene_identity import canonical

MEMBER = 'registration-artifact.json'
PROFILE = 'cospace.registration-artifact/0.1'


def validate_selection(value, *, preflight=False):
    fields = {'registration_revision', 'source_manifest_sha256'} | (set() if preflight else {'snapshot_sha256'})
    require(type(value) is dict and set(value) == fields, 'registration_selection_invalid')
    require(type(value['registration_revision']) is int and 1 <= value['registration_revision'] <= 1000,
            'registration_selection_invalid')
    for key in fields - {'registration_revision'}:
        require(type(value[key]) is str and re.fullmatch('[a-f0-9]{64}', value[key]) is not None,
                'registration_selection_invalid')


def preflight(service, source, selection):
    validate_selection(selection, preflight=True)
    require(selection['source_manifest_sha256'] == source['source_sha256'], 'registration_source_changed')
    state = service.read(source)
    require(state['adopted_revision'] == selection['registration_revision'], 'registration_adoption_changed')
    approved = state['adopted']
    require(approved is not None, 'registration_not_adopted')
    period = approved['approval']
    require(instant(period['valid_from']) <= instant(service.clock()) < instant(period['valid_until']),
            'registration_outside_valid_time')
    if approved['geographic_binding'] is not None:
        service.binding(approved['document'], approved['geographic_binding'])
    return {**selection, 'snapshot_sha256': sha256(canonical(approved)).hexdigest()}


def freeze(service, source, selection, model, generated_at):
    validate_selection(selection)
    accepted = preflight(service, source, {key:value for key,value in selection.items() if key != 'snapshot_sha256'})
    require(accepted == selection, 'registration_snapshot_changed')
    approved = service.fixed(source, selection['registration_revision'])
    result = {'profile': PROFILE, 'generated_at': generated_at, 'selection': selection, 'snapshot': approved}
    raw = canonical(result)
    verify(result, model.manifest)
    return {MEMBER: raw}


def verify(artifact, manifest):
    require(type(artifact) is dict and set(artifact) == {'profile','generated_at','selection','snapshot'}
            and artifact['profile'] == PROFILE, 'registration_artifact_invalid')
    instant(artifact['generated_at'])
    choice = artifact['selection']
    validate_selection(choice)
    approved = Snapshot.model_validate(artifact['snapshot']).model_dump()
    require(sha256(canonical(approved)).hexdigest() == choice['snapshot_sha256'], 'registration_snapshot_changed')
    require(approved['revision'] == approved['approved_revision'] == choice['registration_revision']
            and approved['action'] == 'approve' and approved['review_status'] == 'approved'
            and not approved['document']['synthetic'], 'registration_artifact_invalid')
    source = approved['document']['source']
    require(source['manifest_sha256'] == choice['source_manifest_sha256']
            and source['space_id'] == manifest['space_id'] and source['candidate_id'] == manifest['id']
            and source['model_sha256'] == manifest['members']['spatial.npz']['sha256']
            and source['frame_id'] == manifest['frame_id'] and source['unit'] == manifest['unit']
            and source['axes'] == manifest['axes'], 'registration_source_changed')
    require(approved['report'] == evaluate_registration(approved['document'], expected_source=source)
            and approved['report']['calculation_status'] == 'checks_passed', 'registration_artifact_invalid')
    validate_binding(approved['document'], approved['geographic_binding'])
    bounds, model_bounds = approved['approval']['bounds_m'], source['bounds_m']
    require(all(model_bounds[0][i] <= bounds[0][i] < bounds[1][i] <= model_bounds[1][i]
                for i in range(3)), 'registration_artifact_invalid')
    require(instant(approved['approval']['valid_from']) <= instant(artifact['generated_at'])
            < instant(approved['approval']['valid_until']), 'registration_outside_valid_time')
    return approved


def read_fixed(record, model):
    declared = record.get('registration_selection')
    present = MEMBER in record['files']
    require(bool(declared) == present, 'registration_publication_binding')
    if not present:
        return None
    raw = (model.root / MEMBER).read_bytes()
    member = record['files'][MEMBER]
    require(len(raw) <= 1_048_576 and len(raw) == member['bytes']
            and sha256(raw).hexdigest() == member['sha256'], 'registration_publication_binding')
    artifact = json.loads(raw)
    require(artifact['selection'] == declared and declared['source_manifest_sha256'] == record['model_manifest_sha256'],
            'registration_publication_binding')
    verify(artifact, model.manifest)
    return artifact


def geographic_result(artifact, manifest, objects, at):
    if artifact is None:
        return {'profile': 'cospace.registration-geographic-points/0.1', 'status': 'registration_not_included', 'objects': []}
    approved = verify(artifact, manifest)
    period = approved['approval']
    status = ('registration_outside_valid_time' if not instant(period['valid_from']) <= instant(at) < instant(period['valid_until'])
              else 'geographic_binding_not_recorded' if approved['geographic_binding'] is None else 'available')
    return {'profile': 'cospace.registration-geographic-points/0.1', 'status': status, 'crs': 'WGS84',
            'space_id': manifest['space_id'], 'candidate_id': manifest['id'],
            'height_reference': 'ellipsoidal', 'registration_revision': approved['revision'],
            'geographic_binding': approved['geographic_binding'], 'check_metrics': approved['report']['metrics']['check'],
            'objects': project_objects(approved['document'], approved['geographic_binding'], period['bounds_m'], objects)
            if status == 'available' else [], 'robot_ready': False}
