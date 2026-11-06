import pytest
from fastapi.testclient import TestClient
from packages.lifecycle.preview_control import ControlChange
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_impact import seed
from test_preview_distribution import endpoints
from test_platform_business import secured,sign_in
from test_platform_login import runtime


def request(jobs,pubs,space,old,new=None,kind='superseded'):
    report=jobs.controls.report(pubs,space,'publication:'+old['id'])
    return ControlChange(space_id=space,artifact=report['artifact'],expected_revision=report['record']['revision'],
        expected_snapshot_sha256=report['snapshot_sha256'],operation='retire_publication',reason='修正后版本接替',
        retirement_kind=kind,replacement_publication_id=new['id'] if new else None)


def test_retirement_all_paths_history_idempotency_and_no_restore(tmp_path):
    initial,jobs,directory,spaces,ontologies,pubs,old,new,_=seed(tmp_path);space=spaces[0]['id']
    record,model=pubs.read(old['id']);before={p.name:p.read_bytes() for p in model.root.iterdir() if p.is_file()}
    command=request(jobs,pubs,space,old,new)
    saved=jobs.controls.change(pubs,command,'usr_manager');assert saved['lifecycle_state']=='retired'
    assert jobs.controls.change(pubs,command,'usr_manager')==saved
    assert saved['replacement_publication_id']==new['id'] and saved['actor']=='usr_manager'
    assert jobs.controls.report(pubs,space,command.artifact)['actions']==[]
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        for method,path,body in endpoints(record,model):assert client.request(method,path,json=body).status_code==409,path
        assert client.get('/publications/'+new['id']+'/api/preview').status_code==200
    assert {p.name:p.read_bytes() for p in model.root.iterdir() if p.is_file()}==before
    assert pubs.distribution(old['id'])['replacement_publication_id']==new['id']
    from packages.lifecycle.preview_control import PreviewControls
    assert PreviewControls(jobs.root.parent,directory).read(space,command.artifact)==saved


@pytest.mark.parametrize('case',['self','missing','foreign','paused','no_kind','extra_fields'])
def test_invalid_replacement(tmp_path,case):
    _,jobs,_,spaces,_,pubs,old,new,_=seed(tmp_path);space=spaces[0]['id'];cmd=request(jobs,pubs,space,old,new).model_dump()
    if case=='self':cmd['replacement_publication_id']=old['id']
    if case=='missing':cmd['replacement_publication_id']=None
    if case=='foreign':cmd['space_id']=spaces[1]['id']
    if case=='no_kind':cmd['retirement_kind']=None
    if case=='extra_fields':cmd['operation']='pause_distribution'
    if case=='paused':
        from test_preview_control import run
        run(jobs.controls,pubs,space,'publication:'+new['id'],'pause_distribution')
    with pytest.raises(ValueError):jobs.controls.change(pubs,ControlChange(**cmd),'actor')
    assert pubs.distribution(old['id'])['lifecycle_state']=='active'


def test_erroneous_can_retire_before_replacement(tmp_path):
    _,jobs,_,spaces,_,pubs,old,new,_=seed(tmp_path)
    saved=jobs.controls.change(pubs,request(jobs,pubs,spaces[0]['id'],old,kind='erroneous'),'actor')
    assert saved['lifecycle_state']=='retired' and saved['replacement_publication_id'] is None
    command=request(jobs,pubs,spaces[0]['id'],old,new,kind='erroneous')
    saved=jobs.controls.change(pubs,command,'actor')
    assert saved['lifecycle_state']=='retired' and saved['revision']==2 and saved['replacement_publication_id']==new['id']
    assert jobs.controls.report(pubs,spaces[0]['id'],command.artifact)['actions']==[]


@pytest.mark.parametrize('user,allowed',[('usr_local_test',False),('usr_engineer',False),('usr_manager',True)])
def test_secured_retirement(secured,user,allowed):
    _,client,_,_,jobs,_,spaces,_,old,new=secured
    from packages.service.preview_publications import PreviewPublications
    pubs=PreviewPublications(jobs);headers,_=sign_in(secured,user)
    cmd=request(jobs,pubs,spaces[0]['id'],old,new)
    result=client.post('/api/artifact-control/transitions',json=cmd.model_dump(),headers=headers)
    assert result.status_code==(200 if allowed else 403),result.text
    if allowed:assert result.json()['actor']==user
