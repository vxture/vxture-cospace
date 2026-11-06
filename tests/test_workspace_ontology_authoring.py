from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import uuid
import numpy as np
import pytest
from packages.infrastructure.platform_identity import PlatformPrincipal
from packages.ontology.preview_versions import PreviewOntologies
from packages.ontology.workspace_authoring import WorkspaceOntologies,DraftChange,SealDraft
from packages.construction.preview_model import digest
from packages.views.agent.preview_offline import OfflinePreview,export_bundle,sha
from test_platform_business import secured,sign_in
from test_platform_login import runtime


def principal(**changes):
    return replace(PlatformPrincipal('https://platform.example','usr_owner','org_one','ws_one',('workspace:owner',),'owner',1900000000),**changes)

def document():
    value=json.loads(Path('configs/ontology/indoor-equipment-v0.2.json').read_bytes())
    value.update(ontology_id='p21-rules',version='1.0.0',title='P21场景规则')
    return value

def save_body(**changes):
    return dict(draft_id='draft-'+uuid.uuid4().hex,expected_revision=0,request_id=uuid.uuid4().hex,definition=document(),reason='首次规则编辑')|changes

def seal_body(draft):
    return dict(draft_id=draft['draft_id'],expected_revision=draft['revision'],expected_sha256=draft['sha256'])

def store_at(path,user=None):
    shared=PreviewOntologies(path)
    shared.register('configs/ontology/indoor-equipment-v0.2.json')
    return WorkspaceOntologies(path,user or principal())

def test_workspace_draft_history_fixed_version_and_reopen(tmp_path):
    store=store_at(tmp_path/'ontologies');body=save_body()
    first=store.save(DraftChange(**body),'usr_owner')
    assert first['revision']==1 and not first['sealed']
    second=store.save(DraftChange(**body|{'expected_revision':1,'request_id':uuid.uuid4().hex,'reason':'修改名称','definition':document()|{'title':'修订规则'}}),'usr_owner')
    assert second['revision']==2 and second['history'][0]['actor']=='usr_owner'
    record=store.seal(SealDraft(**seal_body(second)),'usr_owner')
    again=store.seal(SealDraft(**seal_body(second)),'usr_owner')
    assert again==record and record['authoring']['revision']==2
    reopened=WorkspaceOntologies(store.root,principal())
    assert reopened.draft(first['draft_id'])['sealed']
    assert reopened.inspect(record['ontology_id'],record['version'],record['sha256'],[{'object_id':'room-1','type_id':'room','properties':{'name':'测试房间'}}])['status']=='passed'
    assert (reopened.path(record['ontology_id'],record['version'])/'definition.json').is_file()
    with pytest.raises(ValueError,match='already_sealed'):
        store.save(DraftChange(**body|{'expected_revision':2,'request_id':uuid.uuid4().hex}),'usr_owner')

def test_replay_and_revision_conflict(tmp_path):
    store=store_at(tmp_path/'rules');body=save_body();first=store.save(DraftChange(**body),'usr_owner')
    assert store.save(DraftChange(**body),'usr_owner')==first
    with pytest.raises(ValueError,match='request_conflict'):store.save(DraftChange(**body|{'reason':'other'}),'usr_owner')
    with pytest.raises(ValueError,match='request_conflict'):store.save(DraftChange(**body),'usr_other')
    with pytest.raises(ValueError,match='revision_changed'):store.save(DraftChange(**body|{'request_id':uuid.uuid4().hex}),'usr_owner')
    with pytest.raises(ValueError,match='revision_changed'):store.seal(SealDraft(**seal_body(first)|{'expected_sha256':'0'*64}),'usr_owner')

def test_concurrent_revision_has_one_winner(tmp_path):
    store=store_at(tmp_path/'rules');body=save_body()
    def change(_):
        try:store.save(DraftChange(**body|{'request_id':uuid.uuid4().hex}),'usr_owner');return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(change,range(2))).count(True)==1
    assert store.draft(body['draft_id'])['revision']==1

@pytest.mark.parametrize('change',[{'workspace_id':'ws_two'},{'org_id':'org_two'},{'issuer':'https://other.example'}])
def test_scope_isolation(tmp_path,change):
    store=store_at(tmp_path/'rules');draft=store.save(DraftChange(**save_body()),'usr_owner');record=store.seal(SealDraft(**seal_body(draft)),'usr_owner')
    other=WorkspaceOntologies(store.root,principal(**change))
    assert not other.drafts() and len(other.list())==1
    with pytest.raises(ValueError,match='not_found'):other.read(record['ontology_id'],record['version'],record['sha256'])
    assert not other.private_root.exists()

def test_shared_templates_cannot_be_overwritten(tmp_path):
    store=store_at(tmp_path/'rules');value=json.loads(Path('configs/ontology/indoor-equipment-v0.2.json').read_bytes())
    original=store.read(value['ontology_id'],value['version'])[0]
    draft=store.save(DraftChange(**save_body(definition=value|{'title':'更改模板'})),'usr_owner')
    with pytest.raises(ValueError,match='shared_template_read_only'):store.seal(SealDraft(**seal_body(draft)),'usr_owner')
    assert store.read(value['ontology_id'],value['version'])[0]==original

@pytest.mark.parametrize('mutation',[
    lambda d:d['types']['room']['properties']['name'].update(min_length=200,max_length=1),
    lambda d:d['relations']['contains'].update(target_types=['missing']),
    lambda d:d['relations']['connected_to'].update(symmetric=False),
    lambda d:d.update(version='invalid'),
    lambda d:d.update(extra='invalid'),
])
def test_invalid_drafts_save_but_cannot_seal(tmp_path,mutation):
    store=store_at(tmp_path/'rules');value=document();mutation(value)
    draft=store.save(DraftChange(**save_body(definition=value)),'usr_owner')
    assert store.validate(value)['status']=='failed'
    with pytest.raises(ValueError,match='definition_invalid'):store.seal(SealDraft(**seal_body(draft)),'usr_owner')
    assert not draft['sealed']

def test_corrupt_history_refuses_read(tmp_path):
    store=store_at(tmp_path/'rules');draft=store.save(DraftChange(**save_body()),'usr_owner')
    with sqlite3.connect(store.db) as db:
        event=draft['history'][0]|{'actor':'forged'};db.execute('UPDATE events SET record=?',(json.dumps(event),))
    with pytest.raises(ValueError,match='integrity'):store.drafts()

@pytest.mark.parametrize('user,owner',[('usr_manager',False),('usr_engineer',False),('usr_local_test',False),('usr_owner',True)])
def test_authoring_http_roles_and_scoped_routes(secured,user,owner):
    rp,c,accounts,_,jobs,*_=secured
    if owner:accounts.roles=['workspace:owner']
    headers,_=sign_in(secured,user)
    response=c.get('/api/ontology-authoring');assert response.status_code==200
    assert response.json()['can_edit']==owner
    body=save_body();response=c.post('/api/ontology-authoring/drafts',json=body,headers=headers)
    assert response.status_code==(200 if owner else 403),response.text
    if not owner:return
    draft=response.json();assert draft['actor']==user
    assert c.post('/api/ontology-authoring/seal',json=seal_body(draft),headers=headers).status_code==200
    versions=c.get('/api/ontologies').json()['ontologies'];assert any(v['ontology_id']=='p21-rules' for v in versions)
    record=next(v for v in versions if v['ontology_id']=='p21-rules')
    assert c.get('/api/ontologies/p21-rules/1.0.0',params={'sha256':record['sha256']}).status_code==200
    assert c.post('/api/ontologies/p21-rules/1.0.0/validate',json={'sha256':record['sha256'],'objects':[{'object_id':'x','type_id':'room','properties':{'name':'测试'}}]},headers=headers).json()['status']=='passed'
    accounts.workspace='ws_other';sign_in(secured,user)
    assert c.get('/api/ontology-authoring').json()['drafts']==[]
    assert not any(v['ontology_id']=='p21-rules' for v in c.get('/api/ontologies').json()['ontologies'])
    assert c.get('/api/ontologies/p21-rules/1.0.0',params={'sha256':record['sha256']}).status_code==404

def test_owner_seal_to_actual_semantic_publication_and_offline(secured):
    _,c,accounts,_,jobs,_,spaces,*_=secured;accounts.roles=['workspace:owner'];headers,_=sign_in(secured,'usr_owner')
    draft=c.post('/api/ontology-authoring/drafts',json=save_body(),headers=headers).json()
    sealed=c.post('/api/ontology-authoring/seal',json=seal_body(draft),headers=headers);assert sealed.status_code==200,sealed.text
    record=sealed.json();base=jobs.model('build-one')
    before=(base.root/'model.json').read_bytes()
    body={'space_id':spaces[0]['id'],'base_candidate_id':'build-one','base_manifest_sha256':digest(base.root/'model.json'),
          'ontology_ref':{k:record[k] for k in ('ontology_id','version','sha256')},
          'objects':[{'object_id':'room-p21','type_id':'room','properties':{'name':'测试房间'},'point_index':0}]}
    response=c.post('/api/semantic-candidates',json=body,headers=headers);assert response.status_code==201,response.text
    model=jobs.model(response.json()['id']);assert (base.root/'model.json').read_bytes()==before
    assert model.objects()['ontology_ref']==body['ontology_ref']
    assert model.manifest['human_view']['ontology_ref']==model.manifest['agent_view']['ontology_ref']
    from packages.service.preview_publications import PreviewPublications
    selected=jobs.selection(body['space_id']);chosen=jobs.select(model.manifest['id'],selected['revision'],body['space_id'])
    pubs=PreviewPublications(jobs);release=pubs.publish(model.manifest['id'],chosen['revision'],body['space_id'])
    _,fixed=pubs.read(release['id']);raw=export_bundle(release,fixed);offline=OfflinePreview(raw,release['id'],sha(raw))
    assert offline.objects()==c.get(release['preview_url']+'api/objects').json()

@pytest.mark.parametrize('user,status',[('usr_local_test',403),('usr_engineer',200),('usr_manager',200),('usr_other',403)])
def test_anchor_preview_authorization_and_mapping(secured,user,status):
    _,c,_,_,jobs,_,spaces,*_=secured;sign_in(secured,user)
    if status==200:
        path=jobs.root/'build-one/output/model.json';model=json.loads(path.read_bytes());model['axes']=['right','down','forward'];path.write_text(json.dumps(model))
    response=c.get('/candidates/build-one/api/anchor-preview');assert response.status_code==status,response.text
    if status!=200:return
    data=response.json();assert data['candidate_id']=='build-one' and data['space_id']==spaces[0]['id']
    model=jobs.model('build-one');assert data['manifest_sha256']==digest(model.root/'model.json')
    with np.load(model.root/'spatial.npz') as arrays:
        assert np.array_equal(arrays['points'][::data['sampling']['stride']],data['points'])
    assert c.get('/candidates/build-two/api/anchor-preview').status_code==403

def test_authoring_csrf_extra_fields_and_empty_reason(secured):
    _,c,accounts,*_=secured;accounts.roles=['workspace:owner'];headers,_=sign_in(secured,'usr_owner');body=save_body()
    assert c.post('/api/ontology-authoring/drafts',json=body).status_code==403
    assert c.post('/api/ontology-authoring/drafts',json=body|{'actor':'forged'},headers=headers).status_code==422
    assert c.post('/api/ontology-authoring/drafts',json=body|{'reason':'   '},headers=headers).status_code==409


def test_anchor_preview_missing_axes_does_not_invent_coordinates(secured):
    _,c,_,_,jobs,*_=secured;sign_in(secured,'usr_manager')
    path=jobs.root/'build-one/output/model.json';model=json.loads(path.read_bytes());model.pop('axes',None);path.write_text(json.dumps(model))
    response=c.get('/candidates/build-one/api/anchor-preview')
    assert response.status_code==409 and response.json()['detail']=='anchor_coordinate_axes_unavailable'


def test_authoring_and_anchor_json_contracts(secured):
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
    def schema(name):return Draft202012Validator(json.loads(Path('contracts/schemas/'+name+'-v0.1.schema.json').read_bytes()))
    body=save_body();schema('ontology-draft-change').validate(body)
    with pytest.raises(ValidationError):schema('ontology-draft-change').validate(body|{'actor':'client_spoof'})
    schema('ontology-draft-seal').validate({'draft_id':body['draft_id'],'expected_revision':1,'expected_sha256':'a'*64})
    _,c,_,_,jobs,*_=secured;sign_in(secured,'usr_manager')
    path=jobs.root/'build-one/output/model.json';model=json.loads(path.read_bytes());model['axes']=['x','y','z'];path.write_text(json.dumps(model))
    data=c.get('/candidates/build-one/api/anchor-preview').json();schema('anchor-preview').validate(data)
    with pytest.raises(ValidationError):schema('anchor-preview').validate(data|{'robot_ready':True})
