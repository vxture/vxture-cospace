import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from packages.service.release_contract import SCHEMA, inspect_release_snapshot
from packages.service.release_sample import build_release_sample


def inspect(files):
    return inspect_release_snapshot(files, now='2026-10-28T00:30:00Z')


def test_schema():
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text(encoding='utf-8')))


def test_complete_snapshot_remains_synthetic():
    files = build_release_sample()
    report = inspect(files)
    assert report['content_integrity_verified']
    assert report['quality']['declared_limits_met']
    assert set(report['verified_members']) == set(files)
    assert not any(report[k] for k in ('authorized','robot_ready','real_release_ready','evidence_semantics_verified'))


@pytest.mark.parametrize('path', ['geometry.json','human-payload.json','assessment.json','ontology.json'])
def test_changed_bytes_rejected(path):
    files = build_release_sample()
    files[path] += b' '
    with pytest.raises(ValueError, match='integrity_mismatch'):
        inspect(files)


@pytest.mark.parametrize('path', ['frame.json','machine.json','check-points.json','coverage.json'])
def test_missing_file(path):
    files = build_release_sample()
    del files[path]
    with pytest.raises(ValueError, match='missing_artifact'):
        inspect(files)


@pytest.mark.parametrize('path,change,message', [
    ('human.json',lambda d:d['source_truth'].update(id='truth-other'),'view_truth_mismatch'),
    ('machine.json',lambda d:d.update(scene_id='different'),'view_truth_mismatch'),
    ('human.json',lambda d:d['frame'].update(id='other'),'view_frame_scope_ontology'),
    ('machine.json',lambda d:d['quality'].update(id='other'),'view_quality_mismatch'),
    ('human.json',lambda d:d.update(object_ids=['invented']),'view_unknown_object'),
    ('machine.json',lambda d:d.update(object_ids=['cabinet-a']),'undeclared_object_subset'),
    ('human.json',lambda d:d['expression'].update(losses=[]),'document_structure'),
    ('machine.json',lambda d:d['expression'].update(validation='validated'),'document_structure'),
    ('human.json',lambda d:d.update(data_kind='real'),'document_structure'),
    ('objects.json',lambda d:d['instances'][0].update(type_id='Pump'),'unknown_object_type'),
    ('objects.json',lambda d:d['instances'][0].update(anchor=[10,2,0]),'out_of_scope'),
    ('objects.json',lambda d:d['instances'][1].update(object_id='cabinet-a'),'duplicate_object_identity'),
    ('scope.json',lambda d:d.update(frame_id='missing'),'frame_or_ontology_mismatch'),
    ('assessment.json',lambda d:d['truth_ref'].update(sha256='1'*64),'quality_truth_mismatch'),
    ('assessment.json',lambda d:d['scope'].update(frame_id='missing'),'quality_scope_mismatch'),
    ('assessment.json',lambda d:d['coverage']['partition_ref'].update(id='missing'),'quality_partition_mismatch'),
    ('assessment.json',lambda d:d['geometry']['check_points_ref'].update(sha256='1'*64),'evidence_digest_mismatch'),
    ('release.json',lambda d:d['views'].__setitem__(1,copy.deepcopy(d['views'][0])),'duplicate_view_identity'),
    ('machine.json',lambda d:d.update(view_kind='human'),'both_view_kinds_required'),
    ('release.json',lambda d:d.update(adoption='approved'),'document_structure'),
    ('truth.json',lambda d:d.update(schema_version='cospace.spatial-release/9'),'document_structure'),
])
def test_rehashed_semantic_conflicts_rejected(path, change, message):
    # All downstream byte digests are recomputed: these test semantics, not hash errors.
    files = build_release_sample({path:change})
    with pytest.raises(ValueError, match=message):
        inspect(files)


def test_explicit_object_subsetting():
    def subset(doc):
        doc['object_ids'] = ['cabinet-a']
        doc['expression']['losses'].append('object_subset')
    assert inspect(build_release_sample({'human.json':subset}))['content_integrity_verified']


def test_quality_failure_not_promoted_to_release_permission():
    report = inspect(build_release_sample({'profile.json':lambda d:d['rule'].update(max_error_m=None)}))
    assert not report['quality']['declared_limits_met']
    assert not report['real_release_ready']


def test_duplicate_json_keys():
    files = build_release_sample()
    files['release.json'] = b'{"kind":"release","kind":"release"}'
    with pytest.raises(ValueError, match='invalid_json'):
        inspect(files)


@pytest.mark.parametrize('name', ['../escape.json','/absolute','C:/absolute','a\\b.json'])
def test_portable_paths(name):
    files = build_release_sample()
    files[name] = b'{}'
    with pytest.raises(ValueError, match='unsafe_snapshot_path'):
        inspect(files)


def test_case_collision():
    files = build_release_sample()
    files['FRAME.json'] = files['frame.json']
    with pytest.raises(ValueError, match='duplicate_snapshot_path'):
        inspect(files)


def test_mutable_payload_rejected():
    files = build_release_sample()
    files['geometry.json'] = bytearray(files['geometry.json'])
    with pytest.raises(ValueError, match='invalid_snapshot_bytes'):
        inspect(files)


def test_extra_unreferenced_file_rejected():
    files = build_release_sample()
    files['extra.json'] = b'{}'
    with pytest.raises(ValueError, match='unreferenced_snapshot_members'):
        inspect(files)


def test_forged_object_denominator_rejected_even_with_matching_profile():
    def profile(d):
        d['rule']['expected_object_count'] = 1
    def assessment(d):
        d['semantics'].update(required_count=1,confirmed_count=1)
    with pytest.raises(ValueError, match='quality_object_set_mismatch'):
        inspect(build_release_sample({'profile.json':profile,'assessment.json':assessment}))


def test_unresolved_check_evidence():
    files = build_release_sample({'assessment.json':lambda d:d['geometry']['check_points_ref'].update(id='missing')})
    with pytest.raises(ValueError, match='unresolved_evidence_reference'):
        inspect(files)


def test_view_digest_does_not_hide_wrong_document_identity():
    files = build_release_sample({'human.json':lambda d:d.update(id='other-human')})
    with pytest.raises(ValueError, match='reference_identity_mismatch'):
        inspect(files)


def test_literal_size_not_float():
    files = build_release_sample({'release.json':lambda d:d['source_truth'].update(bytes=float(d['source_truth']['bytes']))})
    with pytest.raises(ValueError, match='artifact_integrity_mismatch'):
        inspect(files)


def test_committed_example_bytes_match_reproducible_builder():
    root = Path(__file__).resolve().parents[1] / 'examples/spatial-release/synthetic'
    files = {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert files == build_release_sample()
    assert inspect(files)['content_integrity_verified']
