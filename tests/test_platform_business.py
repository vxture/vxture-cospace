import json
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.infrastructure.platform_identity import IdentityUnavailable
from packages.service.space_access import SpaceAccessPolicy
from packages.service.platform_auth_http import create_auth_app
from packages.service.platform_business_http import BusinessAccess
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_platform_login import runtime, login, activity
from test_preview_workflow import prepared, inventory


@pytest.fixture
def secured(runtime,tmp_path):
    rp,_,accounts,clock=runtime
    (tmp_path/'sample').mkdir()
    initial,jobs,directory,spaces,ontologies,pubs,old,new=prepared(tmp_path/'sample')
    accounts.roles=['workspace:member']
    value={'bindings':[{'issuer':rp.config.issuer,'space_id':s['id'],'org_id':'org_mock','workspace_id':'ws_mock'} for s in spaces],
        'grants':[{'issuer':rp.config.issuer,'subject':user,'space_id':spaces[0]['id'],'role':role}
                  for user,role in [('usr_local_test','viewer'),('usr_engineer','engineer'),('usr_manager','manager')]]
                 +[{'issuer':rp.config.issuer,'subject':'usr_other','space_id':spaces[1]['id'],'role':'viewer'}]}
    policies=SpacePolicyStore(tmp_path/'policy');policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=0,actor='test',reason='fixture')
    app=create_auth_app(rp,business=create_app(initial,jobs,space_directory=directory,ontologies=ontologies,platform_origin=rp.config.origin),
        access=BusinessAccess(rp,policies,directory,jobs))
    with TestClient(app,base_url=rp.config.origin,follow_redirects=False) as client:
        yield rp,client,accounts,clock,jobs,directory,spaces,policies,old,new


def sign_in(secured,user='usr_local_test'):
    rp,client,accounts,*_=secured;accounts.subject=user
    _,sid=login(rp,client,accounts)
    csrf=client.get('/api/auth/session').json()['csrf']
    return {'Origin':rp.config.origin,'X-CoSpace-CSRF':csrf},sid


@pytest.mark.parametrize('user',['usr_local_test','usr_other','usr_engineer','usr_manager'])
def test_build_retry_requires_original_scene_and_input_authorization(secured,monkeypatch,user):
    _,client,_,_,jobs,_,spaces,*_=secured;headers,_=sign_in(secured,user)
    path=jobs.root/'build-one/job.json';previous=json.loads(path.read_bytes());previous.update(state='failed',method='rebuild_from_frozen_rgbd_and_existing_poses');path.write_text(json.dumps(previous))
    calls=[]
    monkeypatch.setattr(jobs,'retry',lambda space,old,request:calls.append((space,old,request)) or {'created':True,'job':previous})
    body={'space_id':spaces[0]['id'],'retry_of':'build-one','request_id':'a'*32}
    assert client.post('/api/build-retries',json=body).status_code==403
    response=client.post('/api/build-retries',json=body,headers=headers)
    assert response.status_code==(202 if user in ('usr_engineer','usr_manager') else 403),response.text
    assert len(calls)==(1 if user in ('usr_engineer','usr_manager') else 0)
    calls.clear()
    for wrong in ({'space_id':spaces[1]['id']},{'retry_of':'build-two'},{'retry_of':'../outside'}):
        assert client.post('/api/build-retries',json=body|wrong,headers=headers).status_code==403
    # Even a same-scene task cannot reference a foreign scene's input.
    original=jobs.inputs.read(previous['input_id'])
    foreign=jobs.inputs.register('foreign',original['snapshot'],original['tracking'],spaces[1]['id'])
    previous['input_id']=foreign['id'];path.write_text(json.dumps(previous))
    assert client.post('/api/build-retries',json=body,headers=headers).status_code==403
    assert calls==[]


@pytest.mark.parametrize('user',['usr_local_test','usr_other','usr_engineer','usr_manager'])
def test_view_derivation_and_stage_permissions(secured,monkeypatch,user):
    _,client,_,_,jobs,_,spaces,*_=secured;headers,_=sign_in(secured,user);calls=[]
    monkeypatch.setattr(jobs,'derive_view',lambda *args:calls.append(args) or {'created':True,'job':{'id':'build-accepted'}})
    monkeypatch.setattr(jobs,'stages',lambda *args:calls.append(args) or {'job_id':'build-one'})
    query={'space_id':spaces[0]['id'],'candidate_id':'build-one'};body=query|{'view_kind':'human','request_id':'b'*32}
    expected=202 if user in ('usr_engineer','usr_manager') else 403
    assert client.post('/api/view-derivations',json=body).status_code==403
    assert client.post('/api/view-derivations',json=body,headers=headers).status_code==expected
    assert client.get('/api/build-stages',params=query).status_code==(200 if expected==202 else 403)
    calls.clear()
    for wrong in ({'candidate_id':'build-two'},{'space_id':spaces[1]['id']},{'candidate_id':'../outside'}):
        assert client.post('/api/view-derivations',json=body|wrong,headers=headers).status_code==403
        assert client.get('/api/build-stages',params=query|wrong).status_code==403
    assert not calls


def test_filtered_directory_and_direct_space_only_authorized(secured):
    rp,c,_,_,jobs,_,spaces,_,_,new=secured
    assert c.get('/api/spaces').status_code==401
    sign_in(secured)
    result=c.get('/api/spaces');assert result.status_code==200,result.text
    data=result.json();assert [s['id'] for s in data['spaces']]==[spaces[0]['id']]
    assert data['spaces'][0]['capabilities']==['space.preview','space.query']
    assert new['id'] in result.text and spaces[1]['id'] not in result.text
    assert c.get('/api/spaces/'+spaces[0]['id']).status_code==200
    assert c.get('/api/spaces/'+spaces[1]['id']).status_code==403
    assert c.get('/api/projects/'+spaces[0]['project_id']).status_code==200
    assert c.get('/api/projects/project-'+'f'*16).status_code==403


@pytest.mark.parametrize('method,suffix',[('GET',''),('HEAD',''),('GET','/preflight'),('HEAD','/preflight'),('POST','/preflight')])
def test_input_scope_hint_must_match_even_when_owner_can_access_both_scenes(secured,monkeypatch,method,suffix):
    _,c,accounts,_,jobs,_,spaces,*_=secured
    accounts.roles=['workspace:owner']
    headers,_=sign_in(secured,'usr_owner')
    identity=json.loads((jobs.root/'build-one/job.json').read_bytes())['input_id']
    path='/api/inputs/'+identity
    assert c.get(path).status_code==200
    assert c.get(path,params={'space_id':spaces[0]['id']}).status_code==200
    def forbidden(*args,**kwargs):pytest.fail('wrong scene must be rejected before payload preflight')
    monkeypatch.setattr('experiments.scripts.serve_nyu_flow_preview.preflight',forbidden)
    assert c.request(method,path+suffix,params={'space_id':spaces[1]['id']},headers=headers).status_code==403


def test_second_user_and_workspace_have_independent_visibility(secured):
    rp,c,accounts,_,_,_,spaces,*_=secured
    sign_in(secured,'usr_other')
    assert [s['id'] for s in c.get('/api/spaces').json()['spaces']]==[spaces[1]['id']]
    assert c.get('/api/spaces/'+spaces[0]['id']).status_code==403
    accounts.workspace='ws_other';sign_in(secured,'usr_local_test')
    assert c.get('/api/spaces').json()['spaces']==[]
    assert c.get('/api/projects').json()['projects']==[]


@pytest.mark.parametrize('suffix',['/','/api/preview','/human.ply','/model.json','/api/objects','/api/lineage'])
def test_viewer_can_browse_fixed_geometry_and_metadata(secured,suffix):
    *_,new=secured;_,c,*_=secured;sign_in(secured)
    r=c.get('/publications/'+new['id']+suffix)
    assert r.status_code==200,r.text[:200]


@pytest.mark.parametrize('suffix',['/offline.zip','/offline.json','/partitions.zip','/partitions.json','/agent.npz','/spatial.npz','/publication.json','/offline-checks.json'])
def test_preview_grant_does_not_allow_export(secured,suffix):
    _,c,*_=secured;new=secured[-1];sign_in(secured)
    assert c.get('/publications/'+new['id']+suffix).status_code==403


def test_engineer_export_and_viewer_query_post_csrf(secured):
    _,c,_,_,_,_,spaces,_,_,new=secured;headers,_=sign_in(secured)
    path='/publications/'+new['id']+'/api/query'
    assert c.post(path,json={'point_m':[0.,0.,2.]}).status_code==403
    r=c.post(path,json={'point_m':[0.,0.,2.]},headers=headers)
    assert r.status_code==200,r.text
    assert r.json()['space_id']==spaces[0]['id']
    sign_in(secured,'usr_engineer')
    assert c.get('/publications/'+new['id']+'/offline.zip').status_code==200


@pytest.mark.parametrize('user,expected',[('usr_engineer',200),('usr_manager',200),('usr_local_test',403),('usr_other',403)])
@pytest.mark.parametrize('suffix',['partitions.json','partitions.zip'])
def test_partition_delivery_obeys_current_scene_export_grant(secured,user,expected,suffix):
    _,client,accounts,_,*_=secured;record=secured[-1]
    path=record['preview_url']+suffix
    assert client.get(path).status_code==401
    sign_in(secured,user)
    response=client.get(path);assert response.status_code==expected,response.text[:200]
    assert response.headers['cache-control']=='no-store'
    if expected==200:
        accounts.workspace='foreign-workspace';sign_in(secured,user)
        assert client.get(path).status_code==403


@pytest.mark.parametrize('route',['/api/selection','/api/semantic-candidates','/api/business-candidates','/api/relation-candidates',
    '/api/builds','/api/batches','/api/inputs','/api/ledger','/api/candidate-comparisons','/api/candidate-reviews','/api/publications'])
def test_viewer_write_denied_before_task_poll_or_source_access(secured,route,monkeypatch):
    _,c,_,_,jobs,_,spaces,*_=secured;headers,_=sign_in(secured)
    def forbidden(*args,**kwargs):pytest.fail('denied request must not poll, preflight or create')
    monkeypatch.setattr(jobs,'poll',forbidden);monkeypatch.setattr(jobs,'start',forbidden)
    monkeypatch.setattr(jobs.inputs,'resolve',forbidden)
    assert c.post(route,json={'space_id':spaces[0]['id'],'candidate_id':'build-one'},headers=headers).status_code==403


def test_role_and_policy_revocation_take_effect_next_request_without_restart(secured):
    rp,c,_,_,_,_,spaces,policies,_,new=secured;_,sid=sign_in(secured)
    before=rp.store.get('session',sid)
    rev,p=policies.load();value=p.model_dump();value['grants']=[g for g in value['grants'] if g['subject']!='usr_local_test']
    policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=rev,actor='test',reason='revoke')
    assert c.get('/api/spaces').json()['spaces']==[]
    assert c.get('/publications/'+new['id']+'/human.ply').status_code==403
    assert rp.store.get('session',sid)==before
    with pytest.raises(ValueError,match='policy_revision_changed'):
        policies.replace(p,expected_revision=rev,actor='test',reason='stale')


def test_missing_policy_never_falls_back_to_preview(secured):
    _,c,_,_,_,_,_,policies,_,new=secured;sign_in(secured);policies.path.unlink()
    assert c.get('/api/spaces').status_code==503
    assert c.get('/publications/'+new['id']+'/').status_code==503


@pytest.mark.parametrize('path',['/api/preview','/api/thumbnail','/api/query','/spatial.npz','/human.ply','/index.html',
    '/docs','/openapi.json','/api/unlisted','/publications//oops','/candidates/build-one/extra/file',
    '/publications/preview-%252e%252e/human.ply','/api/auth/unknown','/auth/unlisted',
    '/api/auth/%2e%2e/%2e%2e/spatial.npz','/workbench/%2e%2e/spatial.npz'])
def test_no_root_static_unknown_route_or_encoding_bypass(secured,path):
    _,c,*_=secured;sign_in(secured)
    response=c.get(path)
    assert response.status_code==(404 if path=='/index.html' else 403)
    assert 'location' not in response.headers


def test_foreign_direct_references_comparison_and_forged_scope_deny(secured):
    _,c,_,_,_,_,spaces,_,_,new=secured;headers,_=sign_in(secured,'usr_manager')
    assert c.get('/candidates/build-two/api/preview').status_code==403
    for route,body in [('/api/selection',{'space_id':spaces[0]['id'],'candidate_id':'build-two','expected_revision':0}),
        ('/api/publication-comparisons',{'space_id':spaces[1]['id'],'base_publication_id':new['id'],'target_publication_id':new['id']}),
        ('/api/semantic-candidates',{'space_id':spaces[0]['id'],'base_candidate_id':'build-two'})]:
        assert c.post(route,json=body,headers=headers).status_code==403
    assert c.get('/api/selection',params=[('space_id',spaces[0]['id']),('space_id',spaces[1]['id'])]).status_code==403
    raw='{"space_id":"'+spaces[0]['id']+'","space_id":"'+spaces[1]['id']+'"}'
    assert c.post('/api/selection',content=raw,headers=headers|{'Content-Type':'application/json'}).status_code==403


def test_head_range_conditional_and_pause_do_not_bypass_auth(secured):
    _,c,_,_,_,_,_,_,_,new=secured
    path='/publications/'+new['id']+'/human.ply'
    assert c.head(path,headers={'Range':'bytes=0-5'}).status_code==401
    sign_in(secured,'usr_other')
    for method in ('get','head'):
        assert getattr(c,method)(path,headers={'Range':'bytes=0-5','If-None-Match':'anything'}).status_code==403


def test_engineer_data_writes_allowed_publish_denied_and_foreign_input_rejected(secured):
    _,c,_,_,jobs,_,spaces,_,_,new=secured;headers,_=sign_in(secured,'usr_engineer')
    body={'space_id':spaces[0]['id'],'name':'access batch','origin':'imported_sample','note':'authorization test'}
    r=c.post('/api/batches',json=body,headers=headers);assert r.status_code==201,r.text
    assert c.get('/api/batches',params={'space_id':spaces[0]['id']}).status_code==200
    assert c.post('/api/publications',json={'space_id':spaces[0]['id'],'candidate_id':new['candidate_id'],'expected_revision':2},headers=headers).status_code==403
    assert c.post('/api/projects',json={'name':'not workspace authority'},headers=headers).status_code==403
    assert c.post('/api/spaces',json={'name':'not bound','project_id':spaces[0]['project_id']},headers=headers).status_code==403


def test_central_unavailable_or_invalid_never_runs_business(secured,monkeypatch):
    rp,c,accounts,clock,_,_,_,_,_,new=secured;headers,sid=sign_in(secured)
    clock[0]+=91
    assert c.get('/publications/'+new['id']+'/').status_code==503
    accounts.valid=False
    assert activity(rp,c).json()['authenticated'] is False
    assert c.get('/api/spaces').status_code==401


def test_store_restart_and_history_are_persistent(secured):
    *_,policies,old,new=secured
    restarted=SpacePolicyStore(policies.path.parent)
    revision,p=restarted.load();assert revision==1
    with sqlite3.connect(policies.path) as db:
        saved=json.loads(db.execute('SELECT record FROM history WHERE revision=1').fetchone()[0])
    assert saved['actor']=='test' and saved['reason']=='fixture'


def test_manager_publish_pause_restore_and_viewer_still_cannot_export(secured):
    _,c,_,_,jobs,_,spaces,_,_,new=secured
    headers,_=sign_in(secured,'usr_manager')
    r=c.post('/api/publications',json={'space_id':spaces[0]['id'],'candidate_id':new['candidate_id'],
        'expected_revision':jobs.selection(spaces[0]['id'])['revision']},headers=headers)
    assert r.status_code==201,r.text
    identity=r.json()['id'];artifact='publication:'+identity
    report=c.get('/api/artifact-control',params={'space_id':spaces[0]['id'],'artifact':artifact})
    assert report.status_code==200,report.text
    # Use actual report contract, as the product does, rather than bypassing control.
    value=report.json()
    request={'space_id':spaces[0]['id'],'artifact':artifact,'expected_revision':0,
        'expected_snapshot_sha256':value['snapshot_sha256'],'operation':'pause_distribution','reason':'access integration'}
    r=c.post('/api/artifact-control/transitions',json=request,headers=headers)
    assert r.status_code==200,r.text
    assert c.get('/publications/'+identity+'/human.ply').status_code==409
    sign_in(secured,'usr_other')
    assert c.get('/publications/'+identity+'/human.ply').status_code==403
    headers,_=sign_in(secured,'usr_manager')
    value=c.get('/api/artifact-control',params={'space_id':spaces[0]['id'],'artifact':artifact}).json()
    request.update(expected_revision=1,expected_snapshot_sha256=value['snapshot_sha256'],operation='restore')
    r=c.post('/api/artifact-control/transitions',json=request,headers=headers)
    assert r.status_code==200,r.text
    sign_in(secured)
    assert c.get('/publications/'+identity+'/human.ply').status_code==200
    assert c.get('/publications/'+identity+'/offline.zip').status_code==403
