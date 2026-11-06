import json
import pytest
from fastapi.testclient import TestClient
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_registration import PreviewRegistration
from packages.construction.preview_jobs import PreviewJobs
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.preview_offline import OfflinePreview,export_bundle,sha
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_inputs import source
from test_preview_publications import fixture


def setup(tmp_path):
    initial,jobs=fixture(tmp_path)
    directory=PreviewSpaces(tmp_path/'directory')
    project=directory.create('project','test')
    spaces=[directory.create('space',name,project['id']) for name in ('A','B')]
    jobs.directory=directory
    for identity,space in zip(('build-one','build-two'),spaces):
        ownership={k:space[k] for k in ('project_id',)}|{'space_id':space['id']}
        path=jobs.root/identity/'job.json'; job=json.loads(path.read_bytes())
        job.update(ownership); path.write_text(json.dumps(job),encoding='utf-8')
        path=jobs.root/identity/'output'/'model.json'; model=json.loads(path.read_bytes())
        model.update(ownership); model['source']={'input_binding':ownership}
        path.write_text(json.dumps(model),encoding='utf-8')
    return initial,jobs,directory,spaces


def test_registration_deduplicates_only_within_same_space_and_rejects_wrong_build(tmp_path):
    _,jobs,directory,(a,b)=setup(tmp_path)
    snapshot,tracking=source(tmp_path)
    catalog=PreviewInputs(tmp_path/'catalog',directory); jobs.inputs=catalog
    registration=PreviewRegistration(catalog,{'public':{'label':'sample','snapshot':snapshot,'tracking':tracking}})
    legacy=registration.register('public','legacy')['input']
    first=registration.register('public','public sample A',a['id'])
    second=registration.register('public','public sample B',b['id'])
    assert first['created'] and second['created']
    assert len({legacy['id'],first['input']['id'],second['input']['id']})==3
    assert not registration.register('public','again',a['id'])['created']
    before=jobs.list()
    for space_id in (None,b['id']):
        with pytest.raises(ValueError,match='space_ownership_mismatch'):
            jobs.start(first['input']['id'],space_id)
    with pytest.raises(ValueError): registration.register('public','bad','../outside')
    assert jobs.list()==before and len(catalog.list())==3


def test_independent_selections_restart_and_scoped_publication(tmp_path):
    _,jobs,directory,(a,b)=setup(tmp_path)
    with pytest.raises(ValueError,match='space_ownership_mismatch'): jobs.select('build-one',0,b['id'])
    with pytest.raises(ValueError,match='space_ownership_mismatch'): jobs.select('build-one',0)
    jobs.select('build-one',0,a['id']); jobs.select('build-two',0,b['id'])
    assert jobs.selection()['revision']==0
    with pytest.raises(ValueError,match='selection_changed'): jobs.select('build-one',0,a['id'])
    publications=PreviewPublications(jobs)
    with pytest.raises(ValueError,match='space_ownership_mismatch'): publications.publish('build-one',1,b['id'])
    record=publications.publish('build-one',1,a['id'])
    assert record['space_id']==a['id'] and record['project_id']==a['project_id']
    assert not list(publications.root.glob('.pending-*'))
    restarted=PreviewJobs(jobs.root,tmp_path/'unused',tmp_path/'unused')
    restarted.directory=PreviewSpaces(directory.root)
    assert restarted.selection(a['id'])['candidate_id']=='build-one'
    assert restarted.selection(b['id'])['candidate_id']=='build-two'
    assert restarted.selection()['candidate_id'] is None
    assert PreviewPublications(restarted).read(record['id'])[0]==record


def test_api_filters_scope_no_legacy_fallback_and_offline_binding(tmp_path):
    initial,jobs,directory,(a,b)=setup(tmp_path)
    with TestClient(create_app(initial,jobs,space_directory=directory)) as client:
        query={'space_id':a['id']}
        assert client.get('/api/builds').json()['jobs']==[]
        assert [j['id'] for j in client.get('/api/builds',params=query).json()['jobs']]==['build-one']
        assert client.get('/api/workspace-model',params=query).status_code==404
        assert client.get('/api/builds?space_id=unknown').status_code==404
        selection={'candidate_id':'build-one','expected_revision':0,**query}
        assert client.post('/api/selection',json=selection|{'space_id':b['id']}).status_code==409
        assert client.post('/api/selection',json=selection).status_code==200
        assert client.get('/api/workspace-model',params=query).json()['space_id']==a['id']
        record=client.post('/api/publications',json=selection|{'expected_revision':1}).json()
        assert client.get('/api/publications').json()['publications']==[]
        assert client.get('/api/publications',params={'space_id':b['id']}).json()['publications']==[]
        assert client.get('/api/publications',params=query).json()['publications'][0]['id']==record['id']
        raw=client.get(record['preview_url']+'offline.zip').content
        offline=OfflinePreview(raw,record['id'],sha(raw))
        point=[-.05,.05,.05]
        online=client.post(record['query_url'],json={'point_m':point}).json()
        assert online==offline.query(point) and online['space_id']==a['id']
        assert client.get(record['preview_url']+'offline.json').json()['space_id']==a['id']
        checks=client.get(record['preview_url']+'api/checklist').json()
        assert checks['space_id']==a['id']
        assert next(s for s in checks['stages'] if s['id']=='query')['status']=='passed'


def test_model_ownership_tampering_rejected(tmp_path):
    _,jobs,_,(a,b)=setup(tmp_path)
    path=jobs.root/'build-one'/'output'/'model.json'
    model=json.loads(path.read_bytes()); model['space_id']=b['id']
    path.write_text(json.dumps(model),encoding='utf-8')
    with pytest.raises(ValueError,match='space_ownership_mismatch'): jobs.select('build-one',0,a['id'])
    assert jobs.selection(a['id'])['revision']==0
