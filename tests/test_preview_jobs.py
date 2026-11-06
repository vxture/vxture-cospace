import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from packages.construction.preview_jobs import PreviewJobs
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_real_model_preview import make_preview


def test_restart_marks_unfinished_job_interrupted(tmp_path):
    directory=tmp_path/'jobs'/'build-example'; directory.mkdir(parents=True)
    (directory/'job.json').write_text(json.dumps({'id':'build-example','state':'running','created_at':'2026-10-28'}))
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path/'missing',tmp_path/'missing.json')
    assert jobs.list()[0]['state']=='interrupted'
    with pytest.raises(ValueError,match='input_missing'): jobs.start()
    with pytest.raises(ValueError,match='not_available'): jobs.model('../outside')


def test_failure_is_recorded_without_exposing_candidate(tmp_path,monkeypatch):
    snapshot=tmp_path/'snapshot'; snapshot.mkdir(); (snapshot/'report.json').write_text('{}')
    tracking=tmp_path/'tracking.json'; tracking.write_text('{}')
    class Process:
        def poll(self): return 1
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',lambda *a,**kw:Process())
    jobs=PreviewJobs(tmp_path/'jobs',snapshot,tracking)
    first=jobs.start(); assert first['state']=='running'
    record=jobs.list()[0]; assert record['state']=='failed' and record['candidate_url'] is None


def test_job_api_disabled_and_origin_rejection(tmp_path):
    model_dir=tmp_path/'model'; model_dir.mkdir(); make_preview(model_dir)
    with TestClient(create_app(model_dir)) as client:
        assert client.get('/api/builds').json()['enabled'] is False
        assert client.post('/api/builds').status_code==503
        assert client.post('/api/builds',headers={'Origin':'https://example.com'}).status_code==403
        assert client.get('/candidates/not-a-job/').status_code==404


def test_selection_persists_conflict_and_workspace_binding(tmp_path):
    initial=tmp_path/'initial'; initial.mkdir(); make_preview(initial)
    root=tmp_path/'jobs'; candidate=root/'build-test'/'output'; candidate.mkdir(parents=True)
    make_preview(candidate)
    manifest=json.loads((candidate/'model.json').read_bytes()); manifest['id']='build-test'
    (candidate/'model.json').write_text(json.dumps(manifest))
    (candidate.parent/'job.json').write_text(json.dumps({'id':'build-test','state':'succeeded','created_at':'2026-10-28'}))
    jobs=PreviewJobs(root,tmp_path/'snapshot',tmp_path/'tracking')
    assert jobs.selection()['revision']==0
    with TestClient(create_app(initial,jobs)) as client:
        assert client.get('/api/workspace-model').json()['preview_url']=='/'
        request={'candidate_id':'build-test','expected_revision':0}
        assert client.post('/api/selection',json=request,headers={'Origin':'https://example.com'}).status_code==403
        response=client.post('/api/selection',json=request)
        assert response.status_code==200 and response.json()['revision']==1
        assert client.post('/api/selection',json=request).status_code==409
        current=client.get('/api/workspace-model').json()
        assert current['id']=='build-test' and current['preview_url']=='/candidates/build-test/'
        assert client.get(current['thumbnail_url']).status_code==200
        with pytest.raises(ValueError): jobs.select('missing',1)
        assert jobs.selection()['revision']==1
        # Manifest changes must not silently alter the selected version.
        manifest['id']='mutated'; (candidate/'model.json').write_text(json.dumps(manifest))
        assert client.get('/api/workspace-model').status_code==409
    restarted=PreviewJobs(root,tmp_path/'snapshot',tmp_path/'tracking')
    assert restarted.selection()['candidate_id']=='build-test'
    assert len(list((root/'selections').glob('*.json')))==1
