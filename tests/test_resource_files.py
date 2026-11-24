"""Scene-independent files retain ownership, byte integrity and explicit grants."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import sqlite3

import pytest

from packages.data import resource_files
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_workspace_projects import create, associate
from test_workspace_resources import register
from test_resource_sharing import change


def upload(client, headers, project=None, *, payload=b'SYNTHETIC PARK CONTROL NETWORK', **values):
    query = {'name':'control-network.csv', 'owner_kind':'project' if project else 'workspace',
             'is_base':'true', 'request_id':uuid4().hex, 'expected_revision':'0', 'reason':'Synthetic project reference'}
    if project:query['owner_project_id'] = project
    query.update(values)
    return client.post('/api/data-files', params=query, content=payload,
                       headers={'Content-Type':'application/octet-stream'} | headers)


def file_item(client, identity):
    return next(i for i in client.get('/api/data-resources').json()['items'] if i['resource_id']==identity)


def download(client, item, method='GET'):
    return client.request(method, '/api/data-files/download', params={'resource_id':item['resource_id'], 'version_id':item['source_version']['version_id']})


def test_project_upload_needs_no_scene_and_is_fixed_repeat_safe_and_downloadable(secured):
    _, client, _, _, jobs, directory, _, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    project = create(client, headers)['project_id']
    before = {p:p.read_bytes() for p in jobs.inputs.root.rglob('*') if p.is_file()}
    request = uuid4().hex
    response = upload(client, headers, project, request_id=request)
    assert response.status_code==201, response.text
    assert upload(client, headers, project, request_id=request).json()['replayed'] is True
    assert upload(client, headers, project, request_id=request, payload=b'changed').status_code==409
    item = file_item(client, response.json()['resource_id'])
    assert item['kind']=='resource_file' and item['space_id'] is None and item['href'] is None
    assert item['owner_kind']=='project' and item['owner_project_id']==project and item['version_registered']
    assert client.get('/api/data-projects',params={'view':'scenes','project_id':project}).json()['total']==0
    assert before=={p:p.read_bytes() for p in jobs.inputs.root.rglob('*') if p.is_file()}
    raw = download(client,item)
    assert raw.status_code==200 and raw.content==b'SYNTHETIC PARK CONTROL NETWORK'
    assert raw.headers['cache-control']=='no-store' and raw.headers['x-content-type-options']=='nosniff'
    assert raw.headers['content-security-policy'].startswith('sandbox')
    head=download(client,item,'HEAD')
    assert head.status_code==200 and not head.content and int(head.headers['content-length'])==len(raw.content)
    assert register(client,headers,item,project,request_id=uuid4().hex,is_base=False).status_code==200
    assert not file_item(client,item['resource_id'])['is_base']
    # Originals, registrations and audit records share one backup transaction.
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM data_resource_files').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM resource_changes').fetchone()[0]==2


def test_project_member_read_follows_current_project_access_and_cannot_manage(secured):
    _,client,_,_,_,_,scenes,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    a=create(client,headers)['project_id']; b=create(client,headers,1,'b',name='Other')['project_id']
    first=upload(client,headers,a).json(); second=upload(client,headers,b).json()
    a_item=file_item(client,first['resource_id']); b_item=file_item(client,second['resource_id'])
    assert associate(client,headers,scenes[0]['id'],a,2,'c').status_code==200
    member_headers,_=sign_in(secured,'usr_engineer')
    files=[i for i in client.get('/api/data-resources').json()['items'] if i['kind']=='resource_file']
    assert len(files)==1 and files[0]['resource_id']==a_item['resource_id'] and not files[0]['can_manage']
    assert download(client,a_item).status_code==200 and download(client,b_item).status_code==403
    assert upload(client,member_headers,a).status_code==403
    headers,_=sign_in(secured,'usr_manager')
    assert associate(client,headers,scenes[0]['id'],b,3,'d').status_code==200
    sign_in(secured,'usr_engineer')
    assert download(client,a_item).status_code==403 and download(client,b_item).status_code==200


def test_common_file_requires_grant_and_actual_project_reference(secured):
    _,client,_,_,_,_,scenes,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    a=create(client,headers)['project_id']
    assert associate(client,headers,scenes[0]['id'],a,1,'b').status_code==200
    response=upload(client,headers)
    assert response.status_code==201,response.text
    item=file_item(client,response.json()['resource_id'])
    assert item['owner_kind']=='workspace' and item['owner_project_id'] is None
    assert not any(i['resource_id']==item['resource_id'] for i in client.get('/api/data-resources',params={'project_id':a}).json()['items'])
    assert client.get('/api/data-resources',params={'ownership':'workspace'}).json()['total']==1
    grant=change(client,headers,'grant',resource_id=item['resource_id'],version_id=item['source_version']['version_id'],
                 expected_resource_revision=1,target_project_id=a,allow_download=True)
    assert grant.status_code==200,grant.text
    granted=grant.json()['after']
    user_headers,_=sign_in(secured,'usr_engineer')
    assert download(client,item).status_code==403
    assert not any(i['resource_id']==item['resource_id'] for i in client.get('/api/data-resources').json()['items'])
    available=client.get('/api/data-sharing',params={'project_id':a})
    assert available.status_code==200,available.text
    assert available.json()['items'][0]['owner_kind']=='workspace'
    assert change(client,user_headers,'use',grant_id=granted['id'],expected_grant_revision=1,project_id=a,purpose='Reference control network').status_code==200
    row=next(i for i in client.get('/api/data-resources',params={'project_id':a,'ownership':'workspace','placement':'project'}).json()['items'] if i['resource_id']==item['resource_id'])
    assert row['external'] and row['owner_kind']=='workspace' and not row['can_manage']
    url={'grant_id':granted['id'],'project_id':a,'grant_revision':1}
    assert client.get('/api/data-sharing/download',params=url).content==b'SYNTHETIC PARK CONTROL NETWORK'
    headers,_=sign_in(secured,'usr_manager')
    assert change(client,headers,'revoke',grant_id=granted['id'],expected_revision=1).status_code==200
    sign_in(secured,'usr_engineer')
    assert client.get('/api/data-sharing/download',params=url).status_code==403
    assert client.get('/api/data-sharing',params={'view':'uses','project_id':a}).json()['items'][0]['access_status']=='revoked'


@pytest.mark.parametrize('values',[
    {'name':'../escape.txt'}, {'name':'x.exe'}, {'name':'a\n.txt'}, {'owner_kind':'workspace','owner_project_id':'project-'+'a'*16},
    {'owner_kind':'project'}, {'workspace_id':'other'}, {'space_id':'space-'+'a'*16}, {'expected_revision':'1'}])
def test_upload_metadata_fails_before_storage(secured,values):
    _,client,_,_,_,directory,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    assert upload(client,headers,**values).status_code==422
    assert not (directory.root/'business-projects.sqlite3').exists()


def test_upload_limits_csrf_target_archive_and_cross_workspace(secured,monkeypatch):
    _,client,accounts,_,_,directory,*_=secured
    assert upload(client,{}).status_code==401
    headers,_=sign_in(secured,'usr_manager')
    assert upload(client,{}).status_code==403
    assert upload(client,headers,'project-'+'f'*16).status_code==409
    assert upload(client,headers,payload=b'').status_code==413
    monkeypatch.setattr(resource_files,'MAX_STORED_BYTES',5)
    assert upload(client,headers).status_code==409
    monkeypatch.setattr(resource_files,'MAX_STORED_BYTES',512*1024*1024)
    response=upload(client,headers)
    assert response.status_code==201,response.text
    item=file_item(client,response.json()['resource_id'])
    monkeypatch.setattr(resource_files,'MAX_FILES',1)
    assert upload(client,headers).status_code==409
    accounts.workspace='ws_other';accounts.roles=['workspace:owner'];sign_in(secured,'usr_owner')
    assert download(client,item).status_code==403
    assert client.get('/api/data-resources').json()['total']==0


def test_payload_and_metadata_corruption_fail_closed(secured):
    _,client,_,_,_,directory,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    response=upload(client,headers);item=file_item(client,response.json()['resource_id'])
    path=directory.root/'business-projects.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('UPDATE data_resource_files SET payload=?',(b'corrupt',))
    assert download(client,item).status_code==503
    grant=change(client,headers,'grant',resource_id=item['resource_id'],version_id=item['source_version']['version_id'],
                 expected_resource_revision=1,target_kind='workspace',allow_download=True)
    assert grant.status_code==503
    with sqlite3.connect(path) as db:
        raw=json.loads(db.execute('SELECT record FROM data_resource_files').fetchone()[0]);raw['name']='tampered.csv'
        db.execute('UPDATE data_resource_files SET record=?',(json.dumps(raw),))
    assert client.get('/api/data-resources').status_code==503


def test_ownership_cannot_be_switched_by_maintenance_and_project_archive_is_guarded(secured):
    _,client,_,_,_,_,_,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    a=create(client,headers)['project_id']
    response=upload(client,headers,a);item=file_item(client,response.json()['resource_id'])
    assert register(client,headers,item,None,owner_kind='workspace',request_id=uuid4().hex).status_code==409
    archived=client.post('/api/data-projects',headers=headers,json={'action':'update','project_id':a,'name':'Archive','status':'archived','request_id':uuid4().hex,'expected_revision':1,'reason':'Archive synthetic project'})
    assert archived.status_code==409 and archived.json()['detail']=='project_has_managed_resources'
    common=upload(client,headers).json();common_item=file_item(client,common['resource_id'])
    assert register(client,headers,common_item,None,owner_kind='workspace',request_id=uuid4().hex,is_base=False).status_code==200


def test_upload_retry_concurrency_creates_one_resource(secured):
    _,client,_,_,_,directory,*_=secured
    headers,_=sign_in(secured,'usr_manager'); request=uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:upload(client,headers,request_id=request),range(2)))
    assert sorted(r.status_code for r in responses)==[200,201]
    assert len({r.json()['resource_id'] for r in responses})==1
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM data_resource_files').fetchone()[0]==1


def test_stream_budget_and_revocation_during_receive_leave_no_original(secured,monkeypatch):
    from packages.service.space_access import SpaceAccessPolicy
    _,client,_,_,_,directory,_,policies,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    monkeypatch.setattr('packages.service.platform_business_http.MAX_ATTACHMENT_BYTES',3)
    assert upload(client,headers,payload=b'1234').status_code==413
    assert upload(client,headers,payload=iter([b'12',b'34'])).status_code==413
    def revoked():
        yield b'x'
        revision,_=policies.load()
        policies.replace(SpaceAccessPolicy(bindings=[],grants=[]),expected_revision=revision,actor='test',reason='Revoke during file receive')
        yield b'y'
    assert upload(client,headers,payload=revoked()).status_code==403
    assert not (directory.root/'business-projects.sqlite3').exists()


def test_file_original_and_registration_survive_deployment_checkpoint(secured,tmp_path):
    from test_ontology_deployment_checkpoint import module
    _,client,_,_,_,directory,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    response=upload(client,headers)
    assert response.status_code==201
    root=tmp_path/'checkpoint-test'; runtime=root/'data/business/runtime/preview-directory'
    runtime.mkdir(parents=True)
    source=directory.root/'business-projects.sqlite3'; copy=runtime/source.name
    with sqlite3.connect(source) as original,sqlite3.connect(copy) as target:
        original.backup(target)
    checkpoint=module.checkpoint(root,[])
    with sqlite3.connect(checkpoint/source.name) as restored:
        assert restored.execute('SELECT payload FROM data_resource_files').fetchone()[0]==b'SYNTHETIC PARK CONTROL NETWORK'
        assert json.loads(restored.execute('SELECT record FROM data_resources').fetchone()[0])['owner_kind']=='workspace'
        assert restored.execute('SELECT COUNT(*) FROM resource_changes').fetchone()[0]==1


def test_original_storage_reports_trusted_workspace_even_without_scene_bindings(secured):
    from packages.data.resource_storage_usage import stored_bytes
    _,client,_,_,_,directory,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    response=upload(client,headers);item=file_item(client,response.json()['resource_id'])
    # No scene ownership inference is needed: this context was recorded by the
    # authenticated upload in the same transaction as its original.
    first=stored_bytes(directory,[])
    owner=next(iter(first))
    assert owner[1:]==('org_mock','ws_mock') and first[owner]==len(b'SYNTHETIC PARK CONTROL NETWORK')
    assert change(client,headers,'grant',resource_id=item['resource_id'],version_id=item['source_version']['version_id'],
                  expected_resource_revision=1,target_kind='workspace',allow_download=True).status_code==200
    # A separately retained frozen snapshot consumes storage too, once.
    assert stored_bytes(directory,[])[owner]==2*first[owner]
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        db.execute("UPDATE data_resource_scopes SET workspace_id='foreign'")
    with pytest.raises(ValueError):stored_bytes(directory,[])


def test_reference_scope_and_owner_filters_apply_before_directory_deduplication(secured):
    _,client,accounts,_,_,_,scenes,*_=secured
    accounts.roles=['workspace:owner'];headers,_=sign_in(secured,'usr_owner')
    a=create(client,headers)['project_id'];b=create(client,headers,1,'b',name='Inspection')['project_id']
    assert associate(client,headers,scenes[1]['id'],b,2,'c').status_code==200
    response=upload(client,headers,a);item=file_item(client,response.json()['resource_id'])
    grant=change(client,headers,'grant',resource_id=item['resource_id'],version_id=item['source_version']['version_id'],
                 expected_resource_revision=1,target_project_id=b).json()['after']
    assert change(client,headers,'use',grant_id=grant['id'],expected_grant_revision=1,project_id=b,
                  space_id=scenes[1]['id'],purpose='Scene reference').status_code==200
    assert client.get('/api/data-resources',params={'project_id':b,'placement':'project','search':'control-network'}).json()['total']==0
    result=client.get('/api/data-resources',params={'project_id':b,'space_id':scenes[1]['id'],'placement':'scene','search':'control-network'}).json()
    assert result['total']==1 and result['items'][0]['external']
    # The owner can read the original as well. An external-only filter must
    # not lose the use when the unfiltered directory deduplicates its source.
    result=client.get('/api/data-resources',params={'ownership':'external','search':'control-network'}).json()
    assert result['total']==1 and result['items'][0]['external']
    assert client.get('/api/data-resources',params={'ownership':'owned','search':'control-network'}).json()['items'][0]['owner_project_id']==a
