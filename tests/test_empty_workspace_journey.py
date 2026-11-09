import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from experiments.scripts.serve_platform_workbench import assemble
from experiments.scripts.serve_nyu_flow_preview import create_app
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.service.space_access import SpaceAccessPolicy
from test_platform_login import runtime,login,activity


@pytest.fixture
def empty_workspace(runtime,tmp_path):
    rp,_,accounts,*_=runtime
    sources=tmp_path/'sources.json';sources.write_text(json.dumps({'profile':'cospace.preview-sources/0.1','sources':[]}))
    config=tmp_path/'workspace-scenes.json';config.write_text(json.dumps({'profile':'cospace.workspace-scenes/0.1','revision':1,
        'workspaces':[{'issuer':rp.config.issuer,'org_id':'org_mock','workspace_id':'ws_mock','allow_create':True,'creator_subjects':[],'source_bindings':{}}]}))
    policies=SpacePolicyStore(tmp_path/'policies');policies.replace(SpaceAccessPolicy(bindings=[],grants=[]),expected_revision=0,actor='test',reason='empty runtime')
    root=tmp_path/'business'
    with TestClient(assemble(rp,policies,root,None,sources,config),base_url=rp.config.origin,follow_redirects=False) as c:
        yield rp,c,accounts,root,policies,sources,config


def sign_in(env,owner=True):
    rp,c,accounts,*_=env;accounts.subject='usr_owner' if owner else 'usr_member';accounts.roles=['workspace:owner'] if owner else ['workspace:member']
    login(rp,c,accounts);activity(rp,c)
    return {'Origin':rp.config.origin,'X-CoSpace-CSRF':c.get('/api/auth/session').json()['csrf']}


def test_empty_authorized_runtime_creates_first_scene_without_fallback(empty_workspace):
    env=empty_workspace;rp,c,_,root,*_=env;headers=sign_in(env)
    assert c.get('/api/spaces').json()['spaces']==[]
    context=c.get('/api/workspace-scenes').json();assert context['can_create']
    r=c.post('/api/workspace-scenes',json={'request_id':'a'*32,'context_sha256':context['context_sha256'],'name':'First actual scene','description':'No copied model'},headers=headers)
    assert r.status_code==201,r.text
    space=r.json()['space_id']
    assert len(c.get('/api/spaces').json()['spaces'])==1
    assert c.get('/api/inputs',params={'space_id':space}).json()['inputs']==[]
    assert c.get('/api/builds',params={'space_id':space}).json()['jobs']==[]
    assert c.get('/api/publications',params={'space_id':space}).json()['publications']==[]
    assert c.get('/api/workspace-model',params={'space_id':space}).status_code==404
    assert c.get('/api/selection',params={'space_id':space}).json()['candidate_id'] is None
    assert c.get('/api/input-uploads',params={'space_id':space}).status_code==200
    home=c.get('/');assert home.status_code==(200 if Path('apps/workbench/dist/index.html').is_file() else 404)
    assert 'location' not in home.headers
    for path in ('/spatial.npz','/model.json','/api/preview','/api/thumbnail'):
        assert c.get(path).status_code==403,path
    assert not list(root.rglob('job.json')) and not list(root.rglob('spatial.npz'))


def test_empty_runtime_restart_keeps_scene_permission_and_zero_artifacts(empty_workspace):
    env=empty_workspace;rp,c,_,root,policies,sources,config=env;headers=sign_in(env)
    context=c.get('/api/workspace-scenes').json()
    space=c.post('/api/workspace-scenes',json={'request_id':'b'*32,'context_sha256':context['context_sha256'],'name':'Persistent scene'},headers=headers).json()['space_id']
    with TestClient(assemble(rp,policies,root,None,sources,config),base_url=rp.config.origin,follow_redirects=False) as reopened:
        accounts=env[2];login(rp,reopened,accounts);activity(rp,reopened)
        assert reopened.get('/api/spaces').json()['spaces'][0]['id']==space
        assert reopened.get('/api/builds',params={'space_id':space}).json()['jobs']==[]
        assert reopened.get('/api/publications',params={'space_id':space}).json()['publications']==[]


def test_member_cannot_create_or_guess_first_scene(empty_workspace):
    env=empty_workspace;_,c,*_=env;headers=sign_in(env,owner=False)
    assert c.get('/api/workspace-scenes').json()['can_create'] is False
    assert c.post('/api/workspace-scenes',json={},headers=headers).status_code==403
    assert c.get('/api/inputs?space_id=space-'+'a'*16).status_code==403


def test_empty_engineering_entry_requires_explicit_authorized_context():
    with pytest.raises(ValueError,match='authorized_business_configuration'):create_app(None)
