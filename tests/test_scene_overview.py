import json
import pytest
from packages.service.scene_overview import overview
from test_preview_workflow import prepared
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from fastapi.testclient import TestClient
from experiments.scripts.serve_nyu_flow_preview import create_app


def test_overview_reads_selected_metadata_without_polling_or_model_arrays(tmp_path, monkeypatch):
    _, jobs, _, spaces, _, _, _, release = prepared(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('expensive build path called')
    monkeypatch.setattr(jobs, 'list', forbidden)
    monkeypatch.setattr(jobs, 'poll', forbidden)
    monkeypatch.setattr(jobs, 'model', forbidden)
    monkeypatch.setattr(jobs, 'stages', forbidden)
    monkeypatch.setattr(jobs.split, 'frozen', forbidden)
    # Geometry is not needed for descriptive metadata.
    for path in jobs.root.glob('*/output/*.npz'):
        path.unlink()
    result = overview(jobs, spaces[0]['id'])
    assert result['job']['id'] == release['candidate_id']
    assert result['candidate_ref']['candidate_id'] == release['candidate_id']
    assert result['counts'] == {'objects': 3, 'business_bindings': 1, 'object_relations': 1}
    assert result['artifact_members_verified'] is False
    assert result['jobs_polled'] is False


def test_overview_missing_selection_uses_latest_same_scene_without_writes(tmp_path, monkeypatch):
    _, jobs, directory, spaces, *_ = prepared(tmp_path)
    empty = directory.create('space', 'empty overview', spaces[0]['project_id'])
    assert overview(jobs, empty['id'])['job'] is None
    path = jobs.root / 'space-selections' / (spaces[0]['id'] + '.json')
    path.unlink()
    result = overview(jobs, spaces[0]['id'])
    assert result['candidate_ref'] is None
    assert result['counts'] is None
    assert result['job']['space_id'] == spaces[0]['id']
    assert not path.exists()


def test_overview_reads_saved_view_states_and_rejects_cross_model_tasks(tmp_path):
    _, jobs, _, spaces, _, _, _, release = prepared(tmp_path)
    job_path = jobs.root / release['candidate_id'] / 'job.json'
    record = json.loads(job_path.read_bytes())
    ref = {'job_id': record['id'], 'task_id': 'view-' + 'a' * 16}
    record.update(pipeline='model_then_views/0.1', frozen_model={'job_id': record['id']}, view_tasks={'human': ref})
    task_path = jobs.root / ref['job_id'] / 'views' / ref['task_id'] / 'task.json'
    task_path.parent.mkdir(parents=True)
    task = {'id': ref['task_id'], 'job_id': record['id'], 'space_id': record['space_id'],
            'project_id': record['project_id'], 'view_kind': 'human', 'state': 'succeeded',
            'frozen_model': record['frozen_model']}
    task_path.write_text(json.dumps(task)); job_path.write_text(json.dumps(record))
    result = overview(jobs, spaces[0]['id'])
    assert result['stages']['views'] == {'human': {'state': 'succeeded'}}
    task['frozen_model'] = {'job_id': 'build-other'}
    task_path.write_text(json.dumps(task))
    with pytest.raises(ValueError):
        overview(jobs, spaces[0]['id'])


def test_engineering_overview_route_uses_same_saved_summary(tmp_path):
    initial, jobs, directory, spaces, ontologies, *_ = prepared(tmp_path)
    with TestClient(create_app(initial, jobs, space_directory=directory, ontologies=ontologies)) as client:
        response = client.get('/api/scene-overview', params={'space_id': spaces[0]['id']})
    assert response.status_code == 200
    assert response.json()['counts']['objects'] == 3


@pytest.mark.parametrize('field,value', [('candidate_id', '../outside'), ('model_manifest_sha256', '0' * 64), ('space_id', 'other')])
def test_overview_rejects_mismatched_selection(tmp_path, field, value):
    _, jobs, _, spaces, *_ = prepared(tmp_path)
    path = jobs.root / 'space-selections' / (spaces[0]['id'] + '.json')
    doc = json.loads(path.read_bytes()); doc[field] = value; path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        overview(jobs, spaces[0]['id'])


@pytest.mark.parametrize('user,details', [('usr_local_test', False), ('usr_engineer', True)])
def test_overview_http_scope_and_build_permissions(secured, user, details):
    _, client, _, _, jobs, _, spaces, *_ = secured
    sign_in(secured, user)
    response = client.get('/api/scene-overview', params={'space_id': spaces[0]['id']})
    assert response.status_code == 200, response.text
    assert bool(response.json()['job']) is details
    assert client.get('/api/scene-overview', params={'space_id': spaces[1]['id']}).status_code == 403
    assert client.get('/api/scene-overview').status_code == 403
    assert client.get('/api/scene-overview', params={'space_id': spaces[0]['id'], 'extra': '1'}).status_code == 422

def test_overview_warm_read_uses_projection_and_no_job_directory_scan(tmp_path,monkeypatch):
    _,jobs,_,spaces,*_=prepared(tmp_path)
    first=overview(jobs,spaces[0]['id'])
    from pathlib import Path
    original=Path.glob
    def no_job_scan(path,pattern):
        if path==jobs.root:raise AssertionError('overview scanned jobs')
        return original(path,pattern)
    monkeypatch.setattr(Path,'glob',no_job_scan)
    assert overview(jobs,spaces[0]['id'])==first
    selection=jobs.root/'space-selections'/(spaces[0]['id']+'.json')
    selection.unlink()
    result=overview(jobs,spaces[0]['id'])
    assert result['candidate_ref'] is None
    assert result['latest_job']['id']==result['job']['id']


def test_overview_keeps_latest_build_separate_from_selected_candidate(tmp_path):
    _,jobs,_,spaces,*_=prepared(tmp_path)
    previous=overview(jobs,spaces[0]['id'])
    record=dict(previous['job'],id='build-newest',created_at='2099-01-01T00:00:00Z',state='failed',project_id=spaces[0]['project_id'])
    (jobs.root/record['id']).mkdir();jobs.save(record)
    result=overview(jobs,spaces[0]['id'])
    assert result['latest_job']['id']=='build-newest'
    assert result['job']['id']==previous['candidate_ref']['candidate_id']
    assert result['latest_job']['id']!=result['job']['id']


def test_read_model_rebuild_recovers_files_without_read_index(tmp_path):
    _,jobs,_,spaces,*_=prepared(tmp_path)
    import sqlite3
    with sqlite3.connect(jobs.read_model.path) as db:db.execute('DELETE FROM jobs')
    from packages.construction.preview_jobs import PreviewJobs
    recovered=PreviewJobs(jobs.root,jobs.snapshot,jobs.tracking,jobs.inputs)
    assert recovered.read_model.latest(spaces[0]['id']) is not None


def test_warm_projection_rechecks_scene_project_ownership(tmp_path):
    _,jobs,directory,spaces,*_=prepared(tmp_path)
    overview(jobs,spaces[0]['id'])
    project=directory.create('project','new owner')
    path=directory.root/'space'/(spaces[0]['id']+'.json')
    record=json.loads(path.read_bytes());record['project_id']=project['id']
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='space_ownership_mismatch'):
        overview(jobs,spaces[0]['id'])


def test_overview_response_exposes_safe_timing_segments(secured):
    _,client,_,_,_,_,spaces,*_=secured
    sign_in(secured,'usr_engineer')
    response=client.get('/api/scene-overview',params={'space_id':spaces[0]['id']})
    assert response.status_code==200
    timing=response.headers['server-timing']
    assert 'rp_session;dur=' in timing
    assert 'scene_summary;dur=' in timing
    assert 'token' not in timing
    assert 'usr_engineer' not in timing


def test_read_model_failure_is_explicit_service_unavailable(secured,monkeypatch):
    import sqlite3
    _,client,_,_,jobs,_,spaces,*_=secured
    sign_in(secured,'usr_engineer')
    def unavailable(*args):raise sqlite3.OperationalError('read model unavailable')
    monkeypatch.setattr(jobs.read_model,'cached',unavailable)
    response=client.get('/api/scene-overview',params={'space_id':spaces[0]['id']})
    assert response.status_code==503
    assert response.json()['detail']=='scene_overview_unavailable'
