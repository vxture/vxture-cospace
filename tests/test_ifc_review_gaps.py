from copy import deepcopy
import json
import subprocess
import sys

import pytest

from packages.service.ifc_review_gaps import assess_review_gaps
from packages.spatial.scene_identity import canonical, content_digest
from test_ifc_review_snapshot import review_env, structure_source, build, filled, sha
from test_ifc_type_proposals import ontology, mapping


def assess(result, **kwargs):
    return assess_review_gaps(result['snapshot'], expected_sha256=sha(result['snapshot']),
        design_package=result['design_package'], expected_source=json.loads(result['snapshot'])['source'], **kwargs)


def test_empty_sheet_produces_exact_roles_and_no_invented_coverage(review_env):
    result = build(review_env)
    before = deepcopy(result)
    report = assess(result)
    assert assess(result) == report
    assert result == before
    assert report['sg3']['regions'] == {'status': 'no_regions_provided', 'count': 0,
                                       'without_connection_endpoint_ids': []}
    connections = report['sg3']['connections']
    assert (connections['total'], connections['complete_annotations'], connections['pending_annotations']) == (2, 0, 2)
    door, stair = connections['tasks']
    assert door['source_entity_id'] == 'door'
    assert door['missing_endpoint_roles'] == ['side_a', 'side_b']
    assert stair['missing_endpoint_roles'] == ['lower', 'upper']
    assert all(row['evidence_reference_missing'] for row in connections['tasks'])
    assert report['sg3']['evidence']['status'] == 'no_references'
    assert report['sg4']['semantics']['status'] == 'mapping_not_supplied'
    assert report['sg5']['status'] == 'observations_not_assessed'
    assert len(report['sg5']['source_declared_door_element_ids']) == 1
    assert report['real_release_ready'] is False
    assert report.pop('report_sha256') == content_digest(report)


@pytest.mark.parametrize('partial', [False, True])
def test_partial_and_complete_annotations_remain_unverified(review_env, partial):
    sheet = filled(review_env[2])
    if partial:
        sheet['connections'][0]['endpoints'].pop()
    sheet['areas'].append(dict(sheet['areas'][0], id='isolated'))
    report = assess(build(review_env, worksheet=sheet))
    connections = report['sg3']['connections']
    assert connections['complete_annotations'] == int(not partial)
    assert connections['tasks'][0]['missing_endpoint_roles'] == (['side_b'] if partial else [])
    assert connections['tasks'][0]['evidence_reference_missing'] is False
    assert connections['tasks'][0]['assessment'] == 'unverified'
    assert 'isolated' in report['sg3']['regions']['without_connection_endpoint_ids']
    assert report['sg3']['evidence']['status'] == 'references_only'
    assert 'field_connections' in report['sg3']['not_established_by_snapshot']
    assert report['real_release_ready'] is False


def test_semantic_proposal_is_counted_without_adoption(review_env):
    vocabulary = ontology()
    result = build(review_env, mapping=mapping(vocabulary), ontology_raw=vocabulary)
    report = assess(result, ontology_raw=vocabulary)
    semantics = report['sg4']['semantics']
    assert semantics['status'] == 'proposals_only'
    assert semantics['proposed_count'] == 1
    assert 'door' not in semantics['unmapped_source_entity_ids']
    assert 'stair' in semantics['unmapped_source_entity_ids']
    assert semantics['ontology_bound'] is False
    assert 'fact_adoption' in report['sg4']['not_established_by_snapshot']
    assert report['real_release_ready'] is False


def evidence_sheet(review):
    sheet = filled(review)
    sheet['evidence'][0]['sha256'] = sha(b'drawing')
    sheet['evidence'].append({'id': 'unused', 'sha256': sha(b'unused')})
    return sheet


def test_actual_bytes_receipt_is_bound_to_snapshot_including_unused_refs(review_env, tmp_path):
    result = build(review_env, worksheet=evidence_sheet(review_env[2]))
    root = tmp_path / 'evidence'
    root.mkdir()
    for raw in (b'drawing', b'unused'):
        (root / (sha(raw) + '.bin')).write_bytes(raw)
    before = assess(result)
    report = assess(result, evidence_root=root)
    evidence = report['sg3']['evidence']
    assert evidence['status'] == 'bytes_checked'
    assert evidence['used_evidence_ids'] == ['drawing']
    assert evidence['unused_evidence_ids'] == ['unused']
    assert evidence['receipt']['document_sha256'] == sha(result['snapshot'])
    assert evidence['receipt']['unique_files'] == 2
    assert evidence['meaning_verified'] is False
    assert before['report_sha256'] != report['report_sha256']
    assert report['real_release_ready'] is False
    assert str(root) not in json.dumps(report)


@pytest.mark.parametrize('bad', ['missing', 'changed'])
def test_evidence_failure_rejects_whole_report(review_env, tmp_path, bad):
    result = build(review_env, worksheet=evidence_sheet(review_env[2]))
    (tmp_path / (sha(b'drawing') + '.bin')).write_bytes(b'drawing')
    if bad == 'changed':
        (tmp_path / (sha(b'unused') + '.bin')).write_bytes(b'wrong')
    with pytest.raises(ValueError, match='evidence_'):
        assess(result, evidence_root=tmp_path)


@pytest.mark.parametrize('key,value', [('real_release_ready', True), ('ontology_bound', True),
                                      ('alignment_verified', True)])
def test_rehashed_approval_claim_rejected(review_env, key, value):
    result = build(review_env)
    document = json.loads(result['snapshot'])
    document[key] = value
    result['snapshot'] = canonical(document)
    with pytest.raises(ValueError):
        assess(result)


def test_corrupt_package_or_wrong_pin_cannot_produce_diagnostic_report(review_env):
    result = build(review_env)
    source = json.loads(result['snapshot'])['source']
    with pytest.raises(ValueError, match='snapshot_digest'):
        assess_review_gaps(result['snapshot'], expected_sha256='a' * 64,
                           design_package=result['design_package'], expected_source=source)
    result['design_package'] += b'corrupt'
    with pytest.raises(ValueError):
        assess(result)


def test_cli_creates_report_and_preserves_existing_output(review_env, tmp_path):
    result = build(review_env)
    snapshot, design, source, output = [tmp_path / name for name in ('snapshot.json', 'design.bin', 'source.json', 'report.json')]
    snapshot.write_bytes(result['snapshot'])
    design.write_bytes(result['design_package'])
    source.write_text(json.dumps(json.loads(result['snapshot'])['source']), encoding='utf-8')
    command = [sys.executable, '-m', 'experiments.scripts.ifc_review_gaps', '--snapshot', str(snapshot),
               '--snapshot-sha256', sha(result['snapshot']), '--design-package', str(design),
               '--source', str(source), '--output', str(output)]
    subprocess.run(command, capture_output=True, check=True)
    assert json.loads(output.read_bytes()) == assess(result)
    before = output.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert output.read_bytes() == before
