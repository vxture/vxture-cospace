"""F04 verifies a caller-provided immutable byte snapshot, not a production release."""
import hashlib
import json
import math
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from packages.service.sample import read_json
from packages.spatial.quality_contract import evaluate_quality, validate_quality_document

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/schemas/spatial-release-v0.1.schema.json'


def inspect_release_snapshot(files, entry='release.json', *, now):
    """files maps portable relative names to bytes. Does not read paths or URLs."""
    if not isinstance(files, dict) or len(files) > 128:
        raise ValueError('invalid_snapshot_catalog')
    snapshot = dict(files)
    folded = set()
    total = 0
    for path, raw in snapshot.items():
        if (not isinstance(path, str) or not path or '\\' in path or re.search(r'[:\x00-\x1f]', path)
                or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in path.split('/'))):
            raise ValueError('unsafe_snapshot_path')
        if path.casefold() in folded:
            raise ValueError('duplicate_snapshot_path')
        folded.add(path.casefold())
        if type(raw) is not bytes or len(raw) > 8388608:
            raise ValueError('invalid_snapshot_bytes')
        total += len(raw)
    if total > 67108864:
        raise ValueError('snapshot_budget_exceeded')
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema)
    bindings = {}
    seen_ids = {}
    checked = set()

    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('nonfinite_number')
        if isinstance(value, dict):
            for v in value.values():
                finite(v)
        elif isinstance(value, list):
            for v in value:
                finite(v)

    def load(path, kind=None):
        if path not in snapshot:
            raise ValueError('missing_artifact')
        try:
            doc = read_json(snapshot[path])
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ValueError('invalid_json') from error
        finite(doc)
        errors = list(validator.iter_errors(doc))
        if errors or not isinstance(doc, dict) or doc.get('kind') != kind:
            raise ValueError(f'document_structure:{path}')
        if doc['id'] in seen_ids and seen_ids[doc['id']] != path:
            raise ValueError('duplicate_document_identity')
        seen_ids[doc['id']] = path
        return doc

    def verify(ref):
        path = ref['path']
        if path not in snapshot:
            raise ValueError('missing_artifact')
        raw = snapshot[path]
        if type(ref['bytes']) is not int or len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('artifact_integrity_mismatch')
        binding = (ref['id'], ref['sha256'], ref['bytes'])
        if path in bindings and bindings[path] != binding:
            raise ValueError('conflicting_artifact_binding')
        if ref['id'] in seen_ids and seen_ids[ref['id']] != path:
            raise ValueError('duplicate_document_identity')
        bindings[path] = binding
        seen_ids[ref['id']] = path
        checked.add(path)
        return raw

    def document(ref, kind):
        verify(ref)
        doc = load(ref['path'], kind)
        if doc['id'] != ref['id']:
            raise ValueError('reference_identity_mismatch')
        return doc

    def compact(ref):
        return {k:ref[k] for k in ('id','sha256')}

    release = load(entry, 'release')
    checked.add(entry)
    truth_ref = release['source_truth']
    truth = document(truth_ref, 'truth')
    if truth['scene_id'] != release['scene_id']:
        raise ValueError('scene_mismatch')
    frame = document(truth['frame'], 'frame')
    scope = document(truth['scope'], 'scope')
    ontology = document(truth['ontology'], 'ontology')
    objects = document(truth['objects'], 'objects')
    for key in ('geometry', 'coverage', 'provenance'):
        verify(truth[key])
    if scope['frame_id'] != frame['id'] or objects['frame_id'] != frame['id'] or objects['ontology'] != truth['ontology']:
        raise ValueError('frame_or_ontology_mismatch')
    ids = [o['object_id'] for o in objects['instances']]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate_object_identity')
    for obj in objects['instances']:
        if obj['type_id'] not in ontology['type_ids']:
            raise ValueError('unknown_object_type')
        if any(not a <= p < b for p,a,b in zip(obj['anchor'], *scope['bounds'])):
            raise ValueError('object_anchor_out_of_scope')

    profile_raw = verify(release['quality_profile'])
    assessment_raw = verify(release['quality_assessment'])
    profile, assessment = read_json(profile_raw), read_json(assessment_raw)
    validate_quality_document(profile)
    validate_quality_document(assessment)
    if profile.get('kind') != 'profile' or assessment.get('kind') != 'assessment':
        raise ValueError('quality_document_kind_mismatch')
    if profile['profile_id'] != release['quality_profile']['id'] or assessment['assessment_id'] != release['quality_assessment']['id']:
        raise ValueError('quality_identity_mismatch')
    expected_scope = {'scope_ref':compact(truth['scope']), 'frame_id':frame['id'],
                      'bounds':scope['bounds'], 'cell_size_m':scope['cell_size_m']}
    if profile['scope'] != expected_scope or assessment['scope'] != expected_scope:
        raise ValueError('quality_scope_mismatch')
    if assessment['truth_ref'] != compact(truth_ref) or assessment['scene_id'] != release['scene_id']:
        raise ValueError('quality_truth_mismatch')
    quality_result = evaluate_quality(profile, assessment, now=now)
    if (assessment['semantics']['target_objects_ref'] != compact(truth['objects'])
            or assessment['semantics']['required_count'] != len(ids)):
        raise ValueError('quality_object_set_mismatch')
    if assessment['coverage']['partition_ref'] != compact(truth['coverage']):
        raise ValueError('quality_partition_mismatch')

    # Compact F03 refs must resolve to registered snapshot bytes by identity+digest.
    def external(ref):
        path = seen_ids.get(ref['id'])
        if path is None:
            raise ValueError('unresolved_evidence_reference')
        raw = snapshot[path]
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('evidence_digest_mismatch')
        checked.add(path)

    # Additional evidence resources are declared in the provenance resource catalog.
    provenance = read_json(snapshot[truth['provenance']['path']])
    if not isinstance(provenance, dict) or set(provenance) != {'resources'} or not isinstance(provenance['resources'], list):
        raise ValueError('invalid_provenance_catalog')
    for ref in provenance['resources']:
        errors = list(Draft202012Validator({'$defs':schema['$defs'], '$ref':'#/$defs/ref'}).iter_errors(ref))
        if errors:
            raise ValueError('invalid_provenance_reference')
        verify(ref)
    for ref in (assessment['procedure_ref'], assessment['coverage']['partition_ref'],
                assessment['semantics']['target_objects_ref'], assessment['geometry']['check_points_ref']):
        external(ref)

    kinds, view_ids = set(), set()
    for ref in release['views']:
        view = document(ref, 'view')
        if view['id'] in view_ids:
            raise ValueError('duplicate_view_identity')
        view_ids.add(view['id'])
        kinds.add(view['view_kind'])
        if view['scene_id'] != release['scene_id'] or view['source_truth'] != truth_ref:
            raise ValueError('view_truth_mismatch')
        if any(view[k] != truth[k] for k in ('frame','scope','ontology')):
            raise ValueError('view_frame_scope_ontology_mismatch')
        if view['quality'] != release['quality_assessment']:
            raise ValueError('view_quality_mismatch')
        if not set(view['object_ids']) <= set(ids):
            raise ValueError('view_unknown_object')
        # Object subsetting must be explicitly stated as a loss of expression.
        if set(view['object_ids']) != set(ids) and 'object_subset' not in view['expression']['losses']:
            raise ValueError('undeclared_object_subset')
        verify(view['derivation'])
        for artifact in view['artifacts']:
            verify(artifact)
    if kinds != {'human','machine'}:
        raise ValueError('both_view_kinds_required')
    if checked != set(snapshot):
        raise ValueError('unreferenced_snapshot_members')
    return {'release_id':release['id'], 'truth_version_id':truth['id'],
            'release_sha256':hashlib.sha256(snapshot[entry]).hexdigest(),
            'view_ids':sorted(view_ids), 'verified_members':sorted(checked),
            'content_integrity_verified':True, 'quality':quality_result,
            'evidence_semantics_verified':False, 'authorized':False,
            'robot_ready':False, 'real_release_ready':False}
