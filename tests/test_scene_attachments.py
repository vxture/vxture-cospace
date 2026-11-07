import json
from pathlib import Path
import pytest

from packages.data.scene_attachments import SceneAttachments, AttachmentRejected, stored_records
from packages.data.preview_inputs import PreviewInputs
from packages.lifecycle.preview_spaces import PreviewSpaces
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def catalog(tmp_path):
    directory = PreviewSpaces(tmp_path / 'directory')
    project = directory.create('project', 'test')
    space = directory.create('space', 'scene', project['id'])['id']
    return PreviewInputs(tmp_path / 'inputs', directory), space


def test_reference_is_scene_owned_immutable_and_repeat_safe(tmp_path):
    inputs, space = catalog(tmp_path)
    source = tmp_path / 'plan.pdf'; source.write_bytes(b'%PDF reference')
    store = SceneAttachments(inputs)
    first = store.register(source, space, '现场平面图.pdf', 'usr_one')
    second = store.register(source, space, '另一个名称.pdf', 'usr_two')
    assert first['created'] and not second['created']
    assert first['attachment']['id'] == second['attachment']['id']
    assert store.list(space)[0]['name'] == '现场平面图.pdf'
    record, raw = store.download(space, first['attachment']['id'])
    assert record['processing'] == 'stored_original' and raw == b'%PDF reference'
    source.write_bytes(b'changed')
    assert store.download(space, first['attachment']['id'])[1] == b'%PDF reference'


@pytest.mark.parametrize('name', ['plan.exe', '../plan.pdf', 'plan:bad.pdf', ' plan.pdf '])
def test_reference_name_and_format_are_rejected(tmp_path, name):
    inputs, space = catalog(tmp_path); source = tmp_path / 'x.pdf'; source.write_bytes(b'x')
    with pytest.raises(AttachmentRejected): SceneAttachments(inputs).register(source, space, name, 'usr')


def test_reference_tamper_and_cross_scene_are_rejected(tmp_path):
    inputs, space = catalog(tmp_path); source = tmp_path / 'x.txt'; source.write_bytes(b'x')
    store = SceneAttachments(inputs); record = store.register(source, space, 'x.txt', 'usr')['attachment']
    folder = inputs.root / 'scene-attachments' / space / record['id']
    (folder / 'original.bin').write_bytes(b'tampered')
    with pytest.raises(AttachmentRejected): store.download(space, record['id'])
    with pytest.raises(AttachmentRejected): list(stored_records(inputs.root, verify=False))


def test_stored_records_rejects_record_outside_scene(tmp_path):
    inputs, space = catalog(tmp_path); root = inputs.root / 'scene-attachments' / space / ('attachment-' + '0' * 16)
    # A malformed folder is rejected before any payload is served.
    root.mkdir(parents=True)
    with pytest.raises(AttachmentRejected): list(stored_records(inputs.root, verify=True))


def test_http_reference_attachment_is_scene_scoped_and_downloadable(secured):
    _, client, _, _, jobs, _, spaces, *_ = secured
    headers, _ = sign_in(secured, 'usr_engineer')
    query = {'space_id': spaces[0]['id'], 'name': '现场说明.txt'}
    assert client.post('/api/scene-attachments', params=query, content=b'hello', headers=headers).status_code == 201
    listed = client.get('/api/scene-attachments', params={'space_id': spaces[0]['id']})
    assert listed.status_code == 200 and listed.json()['attachments'][0]['name'] == '现场说明.txt'
    identity = listed.json()['attachments'][0]['id']
    downloaded = client.get(f'/api/scene-attachments/{identity}', params={'space_id': spaces[0]['id']})
    assert downloaded.status_code == 200 and downloaded.content == b'hello', downloaded.text
    assert downloaded.headers['content-disposition'].startswith("attachment; filename=reference; filename*=UTF-8''")
    assert downloaded.headers['x-content-type-options'] == 'nosniff'
    head = client.head(f'/api/scene-attachments/{identity}', params={'space_id': spaces[0]['id']})
    assert head.status_code == 200 and head.content == b'' and head.headers['content-length'] == '5'
    assert client.get('/api/scene-attachments', params={'space_id': spaces[1]['id']}).status_code == 403
    assert client.post('/api/scene-attachments', params={'space_id': spaces[0]['id'], 'name': 'x.exe'}, content=b'x', headers=headers).status_code == 422


@pytest.mark.parametrize('user,expected', [('usr_local_test',403), ('usr_other',403), ('usr_manager',201)])
def test_attachment_permissions_and_csrf(secured,user,expected):
    _,client,*_=secured
    query={'space_id':secured[6][0]['id'],'name':'reference.txt'}
    assert client.post('/api/scene-attachments',params=query,content=b'x').status_code==401
    headers,_=sign_in(secured,user)
    assert client.post('/api/scene-attachments',params=query,content=b'x').status_code==403
    response=client.post('/api/scene-attachments',params=query,content=b'x',headers=headers)
    assert response.status_code==expected
    assert client.get('/api/scene-attachments',params={'space_id':query['space_id']}).status_code==(200 if expected==201 else 403)


def test_attachment_stream_limit_empty_and_revocation(secured,monkeypatch):
    from packages.service.space_access import SpaceAccessPolicy
    _,client,_,_,jobs,_,spaces,policies,*_=secured
    headers,_=sign_in(secured,'usr_engineer');query={'space_id':spaces[0]['id'],'name':'reference.txt'}
    monkeypatch.setattr('packages.service.platform_business_http.MAX_ATTACHMENT_BYTES',3)
    assert client.post('/api/scene-attachments',params=query,content=b'1234',headers=headers).status_code==413
    assert client.post('/api/scene-attachments',params=query,content=iter([b'12',b'34']),headers=headers).status_code==413
    assert client.post('/api/scene-attachments',params=query,content=b'',headers=headers).status_code in (409,413)
    def revoked():
        yield b'x'
        revision,_=policies.load()
        policies.replace(SpaceAccessPolicy(bindings=[],grants=[]),expected_revision=revision,actor='test',reason='revoke while receiving')
        yield b'y'
    assert client.post('/api/scene-attachments',params=query,content=revoked(),headers=headers).status_code==403
    assert not (jobs.inputs.root/'scene-attachments').exists()


def test_reference_same_bytes_different_scenes_and_concurrency(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    inputs,space=catalog(tmp_path);source=tmp_path/'plan.txt';source.write_bytes(b'reference')
    store=SceneAttachments(inputs)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:store.register(source,space,'plan.txt','usr'),range(2)))
    assert sum(r['created'] for r in results)==1
    project=inputs.directory.read('space',space)['project_id']
    other=inputs.directory.create('space','other',project)['id']
    second=store.register(source,other,'second.txt','usr')
    assert second['created']
    assert store.list(space)[0]['name']=='plan.txt'
    assert store.list(other)[0]['name']=='second.txt'


def test_reference_same_size_change_is_rejected(tmp_path):
    inputs,space=catalog(tmp_path);source=tmp_path/'ref.txt';source.write_bytes(b'original')
    store=SceneAttachments(inputs);saved=store.register(source,space,'ref.txt','usr')['attachment']
    (store.root/space/saved['id']/'original.bin').write_bytes(b'modified')
    with pytest.raises(AttachmentRejected):store.download(space,saved['id'])
    with pytest.raises(AttachmentRejected):store.register(source,space,'ref.txt','usr')
    with pytest.raises(AttachmentRejected):list(stored_records(inputs.root,verify=True))


def test_refs_backup(tmp_path):
    from types import SimpleNamespace
    from packages.infrastructure.platform_usage import StorageInventory
    from packages.infrastructure.preview_backup import backup,restore,tree
    from packages.infrastructure.preview_service_lock import service_guard
    from packages.infrastructure.space_policy_store import SpacePolicyStore
    from packages.service.space_access import SpaceAccessPolicy
    root=tmp_path/'b';runtime_root=root/'runtime'
    directory=PreviewSpaces(runtime_root/'preview-directory')
    project=directory.create('project','test')
    space=directory.create('space','scene',project['id'])['id']
    inputs=PreviewInputs(runtime_root/'preview-inputs',directory)
    jobs=SimpleNamespace(root=runtime_root/'preview-builds');jobs.root.mkdir()
    policy=SpacePolicyStore(root/'policy')
    policy.replace(SpaceAccessPolicy(bindings=[dict(issuer='https://example.test',space_id=space,org_id='org',workspace_id='ws')],grants=[]),
        expected_revision=0,actor='test',reason='test')
    setup=root/'setup';setup.mkdir()
    (setup/'sources.json').write_text('{"profile":"cospace.preview-sources/0.1","sources":[]}')
    (setup/'workspace-scenes.json').write_text('{"profile":"cospace.workspace-scenes/0.1","revision":1,"workspaces":[]}')
    source=tmp_path/'ref.txt';source.write_bytes(b'reference')
    saved=SceneAttachments(inputs).register(source,space,'ref.txt','usr')['attachment']
    inventory=StorageInventory(policy,inputs,jobs)
    folder=inputs.root/'scene-attachments'/space/saved['id']
    assert inventory.snapshot()[0][1]==sum(p.stat().st_size for p in folder.iterdir())
    with service_guard(runtime_root):pass
    before=tree(root);archive=tmp_path/'backup.zip'
    report=backup(root,archive,actor='test',reason='D1 roundtrip')
    root.rename(tmp_path/'evidence')
    assert restore(archive,root,report['sha256'])['status']=='passed'
    assert tree(root)==before
    assert SceneAttachments(inputs).download(space,saved['id'])[1]==b'reference'
    (folder/'original.bin').write_bytes(b'tampered!')
    with pytest.raises(ValueError):backup(root,tmp_path/'bad.zip',actor='test',reason='tampered')
