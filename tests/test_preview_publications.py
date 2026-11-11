import json
import pytest
from fastapi.testclient import TestClient
from packages.construction.preview_jobs import PreviewJobs
from packages.service.preview_publications import PreviewPublications
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_real_model_preview import make_preview


def fixture(tmp_path):
    initial=tmp_path/'initial'; initial.mkdir(); make_preview(initial)
    root=tmp_path/'jobs'
    for identity in ['build-one','build-two']:
        candidate=root/identity/'output'; candidate.mkdir(parents=True); make_preview(candidate)
        manifest=json.loads((candidate/'model.json').read_bytes()); manifest['id']=identity
        (candidate/'model.json').write_text(json.dumps(manifest))
        (candidate.parent/'job.json').write_text(json.dumps({'id':identity,'state':'succeeded','created_at':'2026-10-28'}))
    return initial,PreviewJobs(root,tmp_path/'snapshot',tmp_path/'tracking')


def test_publication_request_replay_is_idempotent(tmp_path):
    _,jobs=fixture(tmp_path)
    jobs.select('build-one',0)
    store=PreviewPublications(jobs)
    request='a'*32
    first=store.publish('build-one',1,request_id=request)
    jobs.select('build-two',1)
    assert store.publish('build-one',1,request_id=request)['id']==first['id']
    with pytest.raises(ValueError,match='publication_request_conflict'):
        store.publish('build-two',2,request_id=request)
    assert len(store.list())==1


def test_publication_stays_fixed_after_selection_and_candidate_changes(tmp_path):
    initial,jobs=fixture(tmp_path); jobs.select('build-one',0)
    with TestClient(create_app(initial,jobs)) as client:
        request={'candidate_id':'build-one','expected_revision':1}
        assert client.post('/api/publications',json=request,headers={'Origin':'https://example.com'}).status_code==403
        response=client.post('/api/publications',json=request); assert response.status_code==201
        record=response.json(); url=record['preview_url']
        jobs.select('build-two',1)
        assert client.post('/api/publications',json=request).status_code==409
        (jobs.root/'build-one'/'output'/'agent.npz').write_bytes(b'changed after publication')
        assert client.get(url+'api/preview').json()['id']=='build-one'
        assert client.get('/api/workspace-model').json()['id']=='build-two'
        query=client.post(url+'api/query',json={'point_m':[-.05,.05,.05]}).json()
        assert query['model_id']=='build-one' and query['publication_id']==record['id']
        assert query['state']=='surface_candidate'
        assert client.get(url+'agent.npz').status_code==200
        assert client.post(url+'api/query',json={'point_m':[0]}).status_code==422
        assert client.get(url+'build.log').status_code==404
        assert len(client.get('/api/publications').json()['publications'])==1
    restarted=PreviewPublications(jobs)
    assert restarted.read(record['id'])[0]==record


def test_unselected_and_mutated_publication_refused(tmp_path):
    _,jobs=fixture(tmp_path); pubs=PreviewPublications(jobs)
    with pytest.raises(ValueError,match='selection_changed'): pubs.publish('build-one',0)
    jobs.select('build-one',0); record=pubs.publish('build-one',1)
    (pubs.root/record['id']/'agent.npz').write_bytes(b'changed')
    with pytest.raises(ValueError,match='integrity'): pubs.read(record['id'])
    assert pubs.list()[0]['id']==record['id']
    with pytest.raises(ValueError): pubs.read('../outside')
