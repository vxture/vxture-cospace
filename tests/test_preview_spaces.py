import pytest
from fastapi.testclient import TestClient
from packages.lifecycle.preview_spaces import PreviewSpaces
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_real_model_preview import make_preview


def test_persist_two_projects_and_space_identity(tmp_path):
    directory=PreviewSpaces(tmp_path/'directory')
    one=directory.create('project','one'); two=directory.create('project','two')
    a=directory.create('space','same name',one['id'],'public sample test')
    b=directory.create('space','same name',two['id'])
    assert a['id']!=b['id'] and a['project_id']!=b['project_id']
    assert a['publication_id'] is None and b['state']=='no_publication'
    restarted=PreviewSpaces(directory.root)
    assert restarted.read('space',a['id'])==a and len(restarted.list('project'))==2
    assert not list(directory.root.rglob('*.pending'))


def test_bad_names_and_references_leave_no_records(tmp_path):
    directory=PreviewSpaces(tmp_path/'directory')
    for name in ('','  ','x'*101):
        with pytest.raises(ValueError): directory.create('project',name)
    with pytest.raises(ValueError): directory.create('space','name','project-missing')
    with pytest.raises(ValueError): directory.read('space','../outside')
    assert directory.list('space')==[] and directory.list('project')==[]


def test_api_creates_only_directory_records(tmp_path):
    model=tmp_path/'model'; model.mkdir(); make_preview(model)
    before={p.name:p.read_bytes() for p in model.iterdir()}
    directory=PreviewSpaces(tmp_path/'directory')
    with TestClient(create_app(model,space_directory=directory)) as client:
        assert client.get('/api/projects').json()=={'projects':[]}
        assert client.post('/api/projects',json={'name':'one'},headers={'Origin':'https://example.com'}).status_code==403
        assert client.post('/api/projects',json={'name':'one','id':'invented'}).status_code==422
        assert client.post('/api/projects',json={'name':' '}).status_code==409
        p=client.post('/api/projects',json={'name':'one'}).json()
        assert client.get('/api/projects/'+p['id']).json()==p
        assert client.post('/api/spaces',json={'name':'test','project_id':'missing'}).status_code==409
        assert client.post('/api/spaces',json={'name':'test','project_id':p['id'],'publication_id':'fake'}).status_code==422
        r=client.post('/api/spaces',json={'name':'test','project_id':p['id'],'description':'sample'})
        assert r.status_code==201
        s=r.json(); assert client.get('/api/spaces/'+s['id']).json()==s
        assert client.get('/api/spaces/space-missing').status_code==404
        assert client.get('/api/spaces').json()['legacy_records']=='unassigned'
        assert client.get('/api/selection').json()['revision']==0
        assert client.get('/api/publications').json()['publications']==[]
    assert {p.name:p.read_bytes() for p in model.iterdir()}==before
