"""P12 presentation states over the existing saved workflow and authority."""
import json
import pytest
from packages.service.preview_workflow import workflow
from packages.service.preview_publications import PreviewPublications
from packages.lifecycle.preview_control import ControlChange
from test_preview_workflow import prepared, inventory
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def test_complete_and_historical_context_are_independent_and_readonly(tmp_path, monkeypatch):
    _, jobs, _, spaces, _, pubs, old, new = prepared(tmp_path)
    monkeypatch.setattr(jobs, 'poll', lambda *a: pytest.fail('no worker polling'))
    monkeypatch.setattr(jobs.inputs, 'resolve', lambda *a: pytest.fail('no source IO'))
    monkeypatch.setattr('packages.views.agent.preview_offline.export_bundle', lambda *a: pytest.fail('no bundle export'))
    before = inventory(tmp_path)
    for publication in (old, new):
        report = workflow(pubs, spaces[0]['id'], publication_id=publication['id'])
        s = report['summary']
        assert s['service_status'] == 'complete' and s['consumer_status'] == 'unobserved'
        assert s['viewing_publication']['publication_id'] == publication['id']
        assert s['viewing_publication']['matches_current'] == (publication == new)
        assert s['primary_action']['values']['publication'] == publication['id']
        assert s['available_publication_count'] == 2
    assert inventory(tmp_path) == before


def test_new_unpublished_candidate_preserves_old_available_release(tmp_path):
    _, _, _, spaces, _, pubs, old, _ = prepared(tmp_path, publish=False)
    s = workflow(pubs, spaces[0]['id'])['summary']
    assert s['service_status'] == 'pending' and s['work']['label'] == '当前候选待发布'
    assert s['available_publication_count'] == 1
    assert s['publications'][0]['publication_id'] == old['id'] and not s['publications'][0]['matches_current']
    assert 'publication' not in s['primary_action']['values']


@pytest.mark.parametrize('state,label', [('queued', '构建排队中'), ('running', '构建进行中'),
    ('failed', '构建失败，需恢复'), ('interrupted', '构建中断，需恢复'), ('views_failed', '视图待恢复')])
def test_explicit_task_does_not_revoke_fixed_versions(tmp_path, state, label):
    _, jobs, _, spaces, _, pubs, _, new = prepared(tmp_path)
    job = jobs.root / 'build-p12-target'; job.mkdir()
    (job / 'job.json').write_text(json.dumps({'id': job.name, 'state': state, **{k:new[k] for k in ('space_id','project_id')}}))
    s = workflow(pubs, spaces[0]['id'], job_id=job.name)['summary']
    assert s['service_status'] == 'complete' and s['available_publication_count'] == 2
    assert s['work']['label'] == label and s['work']['action']['values']['job'] == job.name
    assert s['tracked_job']['is_current'] is False
    assert s['candidate_ref']['candidate_id'] == new['candidate_id']
    # Without explicit tracking, no arbitrary latest job is made the user's target.
    assert workflow(pubs, spaces[0]['id'])['summary']['work']['label'] == '服务端流程已完成'


def test_paused_target_never_falls_back(tmp_path):
    _, jobs, _, spaces, _, pubs, old, new = prepared(tmp_path)
    space = spaces[0]['id']; artifact = 'publication:' + new['id']
    snapshot = jobs.controls.report(pubs, space, artifact)['snapshot_sha256']
    jobs.controls.change(pubs, ControlChange(space_id=space, artifact=artifact, expected_revision=0,
        expected_snapshot_sha256=snapshot, operation='pause_distribution', reason='P12 isolated test'))
    s = workflow(pubs, space, publication_id=new['id'])['summary']
    assert s['viewing_publication']['status'] == 'paused' and s['service_status'] == 'needs_attention'
    assert s['available_publication_count'] == 1
    assert s['primary_action']['module'] == 'delivery' and s['primary_action']['values']['publication'] == new['id']
    assert s['publications'][0]['publication_id'] != s['publications'][1]['publication_id']
    assert next(p for p in s['publications'] if p['publication_id'] == old['id'])['status'] == 'available'


@pytest.mark.parametrize('status,lifecycle,ready', [('not_checked','active',False), ('failed','active',False),
    ('passed','active',True), ('passed','disabled',False), ('registration_changed','active',False)])
def test_explicit_preparation_does_not_change_selected_or_publications(tmp_path, status, lifecycle, ready):
    _, _, _, spaces, _, pubs, _, _ = prepared(tmp_path)
    prep = {'selected_input_id': 'input-target', 'inputs': [{'input_id':'input-target', 'check_status':status, 'lifecycle_state':lifecycle}],
            'detail':'saved evidence only', 'next_action':{'module':'build' if ready else 'data', 'label':'next', 'values':{'space':spaces[0]['id'],'input':'input-target'}}}
    before = inventory(tmp_path)
    s = workflow(pubs, spaces[0]['id'], preparation_report=prep)['summary']
    assert s['work']['label'] == ('资料可用于构建' if ready else '资料待准备')
    assert s['service_status'] == 'complete' and s['available_publication_count'] == 2
    assert inventory(tmp_path) == before


def test_empty_scene_is_pending_without_side_effects(tmp_path):
    _, jobs, directory, spaces, _, _, _, _ = prepared(tmp_path)
    scene = directory.create('space', 'P12 empty', spaces[0]['project_id'])
    before = inventory(tmp_path)
    s = workflow(PreviewPublications(jobs), scene['id'])['summary']
    assert s['service_status'] == 'pending' and not s['publications'] and not s['candidate_ref']
    assert s['primary_action']['module'] == 'data' and inventory(tmp_path) == before


@pytest.mark.parametrize('field', ['job_id', 'publication_id'])
def test_cross_scene_context_rejected(tmp_path, field):
    _, _, _, spaces, _, pubs, _, new = prepared(tmp_path)
    with pytest.raises((ValueError, PermissionError)):
        workflow(pubs, spaces[1]['id'], **{field:new['candidate_id'] if field == 'job_id' else new['id']})


def test_selection_created_during_read_requires_refresh(tmp_path, monkeypatch):
    _, jobs, directory, spaces, _, pubs, _, _ = prepared(tmp_path)
    scene = directory.create('space', 'P12 concurrent', spaces[0]['project_id'])
    from packages.service import scene_progress
    original = scene_progress.progress
    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        (jobs.root/'space-selections'/(scene['id']+'.json')).write_text('{}')
        return result
    monkeypatch.setattr(scene_progress, 'progress', change)
    with pytest.raises(ValueError, match='changed_refresh'):
        workflow(pubs, scene['id'])


def test_viewer_summary_omits_engineering_and_cannot_request_job(secured):
    _, c, _, _, _, _, spaces, _, _, new = secured
    sign_in(secured)
    s = c.get('/api/workflow', params={'space_id':spaces[0]['id'],'publication_id':new['id']})
    assert s.status_code == 200, s.text
    data = s.json()
    assert data['summary']['work'] is None and data['summary']['candidate_ref'] is None
    assert 'preparation' not in data and data['candidate_ref'] is None
    assert data['summary']['primary_action']['allowed']
    assert c.get('/api/workflow', params={'space_id':spaces[0]['id'],'job_id':new['candidate_id']}).status_code == 403
    assert c.get('/api/workflow', params={'space_id':spaces[1]['id'],'publication_id':new['id']}).status_code == 403


def test_engineer_http_exact_context_and_session_expiry_recovery(secured):
    _, c, _, clock, _, _, spaces, _, old, new = secured
    headers, _ = sign_in(secured, 'usr_engineer')
    params = {'space_id':spaces[0]['id'],'job_id':old['candidate_id'],'publication_id':old['id']}
    first = c.get('/api/workflow', params=params)
    assert first.status_code == 200, first.text
    assert first.json()['summary']['candidate_ref']['candidate_id'] == new['candidate_id']
    assert first.json()['summary']['viewing_publication']['publication_id'] == old['id']
    clock[0] += 91
    assert c.get('/api/workflow', params=params).status_code == 503
    assert c.post('/api/auth/session', headers=headers).status_code == 200
    restored = c.get('/api/workflow', params=params)
    assert restored.status_code == 200, restored.text
    assert restored.json()['summary'] == first.json()['summary']
