from copy import deepcopy
import json
import pytest
from packages.service.workflow_guidance import workflow_guidance
from packages.service.preview_workflow import workflow
from packages.service.scene_registrations import RegistrationError
from test_preview_workflow import prepared, inventory

AT = '2026-11-22T00:00:00Z'


class RegistrationFacts:
    def __init__(self, state=None, error=False):
        self.state = state or {'adopted': None, 'review_status': 'empty'}
        self.error = error
        self.calls = []

    def source(self, space, job):
        self.calls.append((space, job))
        if self.error:
            raise RegistrationError('registration_source_axes_unsupported')
        return (space, job)

    def read(self, source):
        return self.state


def approved():
    return {'review_status': 'approved', 'approved_revision': 3, 'adopted_revision': 3,
            'adopted': {'approval': {'valid_from': '2026-11-21T00:00:00Z', 'valid_until': '2026-11-23T00:00:00Z'}}}


@pytest.mark.parametrize('state,error,status', [({}, False, 'pending'), ({}, True, 'needs_attention'),
    ({'review_status': 'submitted', 'adopted': None}, False, 'in_progress')])
def test_reviewed_candidate_goes_to_its_registration_before_publication(tmp_path, state, error, status):
    _, _, _, spaces, _, pubs, _, _ = prepared(tmp_path, publish=False)
    report = workflow(pubs, spaces[0]['id'])
    records = RegistrationFacts(state, error)
    before = inventory(tmp_path)
    result = workflow_guidance(report, records, at=AT)
    assert result['current_step'] == 'registration'
    assert records.calls == [(spaces[0]['id'], report['candidate_ref']['candidate_id'])]
    assert result['primary_action']['values'] == {'space': spaces[0]['id'], 'job': report['candidate_ref']['candidate_id']}
    assert next(s for s in result['steps'] if s['id'] == 'registration')['status'] == status
    assert inventory(tmp_path) == before


def test_adopted_registration_continues_to_association_or_publication_without_a_gate(tmp_path):
    _, _, _, spaces, _, pubs, _, _ = prepared(tmp_path, publish=False)
    report = workflow(pubs, spaces[0]['id'])
    assert workflow_guidance(report, RegistrationFacts(approved()), at=AT)['current_step'] == 'delivery'
    geometry = deepcopy(report)
    geometry['counts'].update(objects=0, business_bindings=0, object_relations=0)
    result = workflow_guidance(geometry, RegistrationFacts(approved()), at=AT)
    assert result['current_step'] == 'association'
    assert result['basis'] == 'saved_records_not_publication_gate'
    for changes in ({'adopted_revision': None}, {'review_status': 'draft'}):
        assert workflow_guidance(report, RegistrationFacts(approved() | changes), at=AT)['current_step'] == 'registration'
    expired = approved()
    expired['adopted']['approval']['valid_until'] = '2026-11-21T12:00:00Z'
    assert workflow_guidance(report, RegistrationFacts(expired), at=AT)['current_step'] == 'registration'


def test_fixed_release_stays_pinned_and_skips_current_registration_reads(tmp_path):
    _, _, _, spaces, _, pubs, old, _ = prepared(tmp_path)
    report = workflow(pubs, spaces[0]['id'], publication_id=old['id'])
    records = RegistrationFacts(error=True)
    result = workflow_guidance(report, records, at=AT)
    assert not records.calls
    assert result['primary_action']['module'] == 'services'
    assert result['primary_action']['values']['publication'] == old['id']
    assert result['target'] == {'kind': 'publication', 'id': old['id']}
    assert next(s for s in result['steps'] if s['id'] == 'registration')['action']['values']['job'] == old['candidate_id']


def test_unselected_job_never_borrows_current_candidate_registration(tmp_path):
    _, jobs, _, spaces, _, pubs, _, _ = prepared(tmp_path)
    report = workflow(pubs, spaces[0]['id'], job_id='build-one')
    records = RegistrationFacts(approved())
    result = workflow_guidance(report, records, at=AT)
    assert not records.calls
    assert result['primary_action']['module'] == 'build'
    assert result['primary_action']['values']['job'] == 'build-one'
    assert next(s for s in result['steps'] if s['id'] == 'registration')['action']['values']['job'] == 'build-one'


def test_readable_selected_candidate_still_requires_saved_result_review(tmp_path):
    _, jobs, _, spaces, _, pubs, _, _ = prepared(tmp_path, publish=False)
    path = jobs.root / 'space-selections' / (spaces[0]['id'] + '.json')
    selection = json.loads(path.read_bytes())
    selection.pop('selection_review')
    path.write_text(json.dumps(selection))
    records = RegistrationFacts(approved())
    result = workflow_guidance(workflow(pubs, spaces[0]['id']), records, at=AT)
    assert not records.calls
    assert result['current_step'] == 'build'
    assert result['primary_action']['module'] == 'build'
    assert result['primary_action']['values']['tab'] == 'flow'


def test_input_target_never_links_to_an_unrelated_selected_model(tmp_path):
    _, _, _, spaces, _, pubs, _, _ = prepared(tmp_path)
    prep = {'selected_input_id': 'input-target', 'inputs': [{'input_id': 'input-target',
            'check_status': 'not_checked', 'lifecycle_state': 'active'}], 'detail': 'saved evidence',
            'next_action': {'module': 'data', 'label': 'next', 'values': {'space': spaces[0]['id'], 'input': 'input-target'}}}
    records = RegistrationFacts(approved())
    result = workflow_guidance(workflow(pubs, spaces[0]['id'], preparation_report=prep), records, at=AT)
    assert not records.calls
    assert result['primary_action']['values']['input'] == 'input-target'
    assert all(step['action'] is None for step in result['steps'] if step['id'] in ('registration', 'association'))
