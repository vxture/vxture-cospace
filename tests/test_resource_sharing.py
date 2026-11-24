"""Cross-project sharing does not confer source-scene permissions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest

from packages.data.scene_attachments import SceneAttachments
from packages.service.space_access import SpaceAccessPolicy
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_workspace_projects import create, associate
from test_workspace_resources import register


def change(client, headers, action, **values):
    return client.post('/api/data-sharing', headers=headers, json={
        'action': action, 'request_id': uuid4().hex, 'expected_revision': 0,
        'reason': 'Synthetic sharing verification'} | values)


@pytest.fixture
def shared(secured):
    _, client, accounts, _, jobs, directory, scenes, policies, *_ = secured
    third = directory.create('space', 'Synthetic control project', scenes[0]['project_id'])
    revision, policy = policies.load()
    value = policy.model_dump()
    value['bindings'].append(value['bindings'][0] | {'space_id': third['id']})
    for grant in value['grants']:
        if grant['subject'] == 'usr_other':
            grant['role'] = 'engineer'
    value['grants'].append(value['grants'][0] | {'subject': 'usr_c', 'space_id': third['id'], 'role': 'engineer'})
    policies.replace(SpaceAccessPolicy.model_validate(value), expected_revision=revision, actor='test', reason='Sharing fixture')
    accounts.roles = ['workspace:owner']
    headers, _ = sign_in(secured, 'usr_owner')
    a = create(client, headers)['project_id']
    b = create(client, headers, 1, 'b', name='Park inspection')['project_id']
    c = create(client, headers, 2, 'c', name='Control project')['project_id']
    for i, (scene, project) in enumerate(zip([*scenes, third], [a, b, c])):
        assert associate(client, headers, scene['id'], project, 3+i, str(i+1)).status_code == 200
    path = jobs.inputs.root / 'sharing-fixture.txt'
    payload = b'SYNTHETIC CAMPUS CONTROL NETWORK\nE,N,U\n100,200,30\n'
    path.write_bytes(payload)
    attachment = SceneAttachments(jobs.inputs).register(path, scenes[0]['id'], 'control-network.txt', 'test')['attachment']
    accounts.roles = ['workspace:member']
    headers, _ = sign_in(secured, 'usr_manager')
    item = next(i for i in client.get('/api/data-resources').json()['items'] if i['kind'] == 'attachment')
    assert register(client, headers, item, a).status_code == 200
    item = item | {'revision': 1, 'version_count': 1, 'registered': True}
    return {'secured': secured, 'client': client, 'headers': headers, 'a': a, 'b': b, 'c': c,
            'item': item, 'payload': payload, 'attachment': attachment, 'directory': directory,
            'jobs': jobs, 'scenes': scenes}


def grant(shared, **values):
    item = shared['item']
    response = change(shared['client'], shared['headers'], 'grant', resource_id=item['resource_id'],
                      version_id=item['source_version']['version_id'], expected_resource_revision=1,
                      target_project_id=shared['b'], allow_download=True, **values)
    assert response.status_code == 200, response.text
    return response.json()['after']


def available(shared, project=None):
    return shared['client'].get('/api/data-sharing', params={'project_id': project or shared['b']})


def download(shared, granted, **values):
    return shared['client'].get('/api/data-sharing/download', params={
        'grant_id': granted['id'], 'project_id': shared['b'], 'grant_revision': granted['revision']} | values)


def use(shared, headers, granted, **values):
    return change(shared['client'], headers, 'use', grant_id=granted['id'],
                  expected_grant_revision=granted['revision'], project_id=shared['b'], purpose='Reference control network', **values)


def test_shared_reference_and_download_never_grant_source_scene_access(shared):
    client, secured = shared['client'], shared['secured']
    granted = grant(shared)
    owner = client.get('/api/data-resources').json()
    assert next(i for i in owner['items'] if i['kind'] == 'attachment')['is_shared'] is True
    headers, _ = sign_in(secured, 'usr_other')
    before = client.get('/api/data-resources', params={'project_id': shared['b']}).json()
    assert not any(i['resource_id'] == shared['item']['resource_id'] for i in before['items'])
    report = available(shared).json()
    assert report['total'] == 1
    assert shared['scenes'][0]['id'] not in json.dumps(report)
    assert shared['attachment']['id'] not in json.dumps(report)
    saved = use(shared, headers, granted)
    assert saved.status_code == 200, saved.text
    assert saved.json()['after']['coordinate_status'] == 'not_applied'
    after = client.get('/api/data-resources', params={'project_id': shared['b']}).json()
    assert after['total'] == before['total']+1
    rows = [i for i in after['items'] if i['resource_id'] == shared['item']['resource_id']]
    assert len(rows) == 1 and rows[0]['external'] and rows[0]['href'] is None and rows[0]['space_id'] is None
    assert rows[0]['uses'][0]['purpose'] == 'Reference control network'
    assert download(shared, granted).content == shared['payload']
    head = client.head('/api/data-sharing/download', params={'grant_id': granted['id'], 'project_id': shared['b'], 'grant_revision': 1})
    assert head.status_code == 200 and not head.content
    assert int(head.headers['content-length']) == len(shared['payload'])
    assert head.headers['cache-control'] == 'no-store' and head.headers['x-content-type-options'] == 'nosniff'
    assert 'attachment;' in head.headers['content-disposition']
    assert client.get('/api/scene-attachments/'+shared['attachment']['id'], params={'space_id': shared['scenes'][0]['id']}).status_code == 403
    assert client.get('/api/spaces/'+shared['scenes'][0]['id']).status_code == 403
    sign_in(secured, 'usr_c')
    assert available(shared).status_code == 403
    assert available(shared, shared['c']).json()['total'] == 0
    assert download(shared, granted).status_code == 403
    assert client.get('/api/data-resources', params={'project_id': shared['c']}).json()['total'] == 0


def test_frozen_attachment_survives_source_changes_and_rechecks_its_bytes(shared):
    granted = grant(shared)
    # Use the attachment store's actual root rather than assuming its layout.
    store = SceneAttachments(shared['jobs'].inputs)
    root = store.root / shared['scenes'][0]['id'] / shared['attachment']['id']
    record = json.loads((root/'record.json').read_bytes())
    record['name'] = 'revised-name.txt'
    (root/'record.json').write_text(json.dumps(record))
    updated = next(i for i in shared['client'].get('/api/data-resources').json()['items'] if i['kind'] == 'attachment')
    assert updated['source_version']['version_id'] != granted['version_id']
    assert updated['version_registered'] is False
    assert register(shared['client'], shared['headers'], updated, shared['a'], request_id=uuid4().hex).status_code == 200
    (root/'original.bin').write_bytes(b'changed source bytes')
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert use(shared, headers, granted).status_code == 200
    response = download(shared, granted)
    assert response.content == shared['payload']
    assert 'control-network.txt' in response.headers['content-disposition']
    assert available(shared).json()['items'][0]['snapshot']['sha256'] == hashlib.sha256(shared['payload']).hexdigest()
    path = shared['directory'].root / 'business-projects.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('UPDATE data_shared_versions SET payload=?', (b'tampered',))
    assert download(shared, granted).status_code == 503


def test_revoke_regrant_keeps_old_reference_inactive_until_explicit_reacceptance(shared):
    granted = grant(shared)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    used = use(shared, headers, granted).json()['after']
    shared['headers'], _ = sign_in(shared['secured'], 'usr_manager')
    assert change(shared['client'], shared['headers'], 'revoke', grant_id=granted['id'], expected_revision=1).status_code == 200
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert available(shared).json()['total'] == 0
    assert download(shared, granted).status_code == 403
    row = next(i for i in shared['client'].get('/api/data-resources', params={'project_id': shared['b']}).json()['items'] if i.get('external'))
    assert row['uses'][0]['access_status'] == 'revoked'
    assert use(shared, headers, granted, expected_revision=1).status_code == 403
    shared['headers'], _ = sign_in(shared['secured'], 'usr_manager')
    renewed = grant(shared, expected_revision=2)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    rows = shared['client'].get('/api/data-sharing', params={'view':'uses','project_id':shared['b']}).json()['items']
    assert rows[0]['access_status'] == 'grant_changed'
    assert download(shared, granted).status_code == 403
    assert use(shared, headers, renewed, expected_revision=used['revision']).status_code == 200
    assert download(shared, renewed).status_code == 200


def test_expiry_and_scope_are_checked_for_every_read_and_replay(shared, monkeypatch):
    at = datetime.now(timezone.utc)
    granted = grant(shared, expires_at=(at+timedelta(days=1)).isoformat())
    headers, _ = sign_in(shared['secured'], 'usr_other')
    request_id = uuid4().hex
    assert use(shared, headers, granted, request_id=request_id).status_code == 200
    assert use(shared, headers, granted, request_id=request_id).json()['replayed'] is True
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return at+timedelta(days=2)
    monkeypatch.setattr('packages.data.workspace_resource_sharing.datetime', Later)
    assert available(shared).json()['total'] == 0
    assert download(shared, granted).status_code == 403
    assert use(shared, headers, granted, request_id=request_id).status_code == 403
    report = shared['client'].get('/api/data-sharing', params={'view':'uses','project_id':shared['b']}).json()
    assert report['items'][0]['access_status'] == 'expired'
    shared['secured'][2].workspace = 'foreign'
    sign_in(shared['secured'], 'usr_other')
    assert available(shared).status_code == 403 and download(shared, granted).status_code == 403


def test_spatial_application_and_wrong_target_scene_are_rejected(shared):
    granted = grant(shared)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    response = use(shared, headers, granted, use_mode='spatial_application')
    assert response.status_code == 409 and response.json()['detail'] == 'resource_spatial_application_requires_verification'
    assert use(shared, headers, granted, space_id=shared['scenes'][0]['id']).status_code == 403
    assert use(shared, headers, granted, space_id=shared['scenes'][1]['id']).status_code == 200
    filtered = shared['client'].get('/api/data-resources', params={'project_id':shared['b'],'space_id':shared['scenes'][1]['id']}).json()
    assert len([i for i in filtered['items'] if i.get('external')]) == 1


def test_sharing_write_authorization_csrf_and_strict_requests(shared):
    client = shared['client']
    granted = grant(shared)
    assert change(client, {}, 'revoke', grant_id=granted['id'], expected_revision=1).status_code == 403
    assert change(client, shared['headers'], 'revoke', grant_id=granted['id'], expected_revision=1, actor='forged').status_code == 422
    assert client.get('/api/data-sharing', params={'workspace_id':'foreign'}).status_code == 422
    assert client.get('/api/data-sharing/download', params={'grant_id':granted['id'],'project_id':shared['b']}).status_code == 422
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert client.get('/api/data-sharing', params={'view':'grants','resource_id':shared['item']['resource_id']}).status_code == 403
    assert change(client, headers, 'revoke', grant_id=granted['id'], expected_revision=1).status_code == 403
    assert change(client, headers, 'grant', resource_id=shared['item']['resource_id'], version_id=granted['version_id'],
                  expected_resource_revision=1, target_project_id=shared['c']).status_code == 403


def test_optimistic_revision_and_idempotent_audit_do_not_duplicate_grants(shared):
    request_id = uuid4().hex
    first = grant(shared, request_id=request_id)
    assert grant(shared, request_id=request_id) == first
    response = change(shared['client'], shared['headers'], 'revoke', grant_id=first['id'], expected_revision=1, request_id=request_id)
    assert response.status_code == 409 and response.json()['detail'] == 'resource_request_id_reused'
    def revoke(_):
        return change(shared['client'], shared['headers'], 'revoke', grant_id=first['id'], expected_revision=1).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(revoke, range(2))) == [200,409]
    with sqlite3.connect(shared['directory'].root/'business-projects.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM data_sharing_changes').fetchone()[0] == 2


def test_unlink_preserves_history_and_project_archive_checks_references(shared):
    granted = grant(shared)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    used = use(shared, headers, granted).json()['after']
    shared['secured'][2].roles = ['workspace:owner']
    headers, _ = sign_in(shared['secured'], 'usr_owner')
    assert associate(shared['client'], headers, shared['scenes'][1]['id'], None, 6, 'd').status_code == 200
    body = {'action':'update','project_id':shared['b'],'name':'Archive inspection','status':'archived',
            'expected_revision':7,'request_id':'f'*32,'reason':'Synthetic archive verification'}
    response = shared['client'].post('/api/data-projects', headers=headers, json=body)
    assert response.status_code == 409 and response.json()['detail'] == 'project_has_resource_references'
    assert change(shared['client'], headers, 'unlink', use_id=used['id'], expected_revision=1).status_code == 200
    assert shared['client'].post('/api/data-projects', headers=headers, json=body).status_code == 200
    report = shared['client'].get('/api/data-sharing', params={'view':'uses','project_id':shared['b']})
    assert report.status_code == 200 and report.json()['items'][0]['access_status'] == 'unlinked'
    with sqlite3.connect(shared['directory'].root/'business-projects.sqlite3') as db:
        assert json.loads(db.execute('SELECT record FROM data_resource_uses').fetchone()[0])['status'] == 'unlinked'
        assert db.execute('SELECT payload FROM data_shared_versions').fetchone()[0] == shared['payload']


def test_metadata_only_grants_and_workspace_scope_do_not_imply_common_ownership(shared):
    client = shared['client']
    item = next(i for i in client.get('/api/data-resources').json()['items'] if i['kind']=='input')
    assert register(client, shared['headers'], item, shared['a'], request_id=uuid4().hex).status_code == 200
    fields = {'resource_id':item['resource_id'],'version_id':item['source_version']['version_id'],
              'expected_resource_revision':1,'target_kind':'workspace','target_project_id':None}
    assert change(client, shared['headers'], 'grant', **fields, allow_download=True).json()['detail'] == 'resource_download_not_supported'
    response = change(client, shared['headers'], 'grant', **fields)
    assert response.status_code == 200, response.text
    granted = response.json()['after']
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert available(shared).json()['items'][0]['snapshot']['payload_available'] is False
    assert use(shared, headers, granted).status_code == 200
    assert download(shared, granted).status_code == 403
    external = next(i for i in client.get('/api/data-resources',params={'project_id':shared['b']}).json()['items'] if i.get('external'))
    assert external['owner_project_id'] == shared['a']
    sign_in(shared['secured'], 'usr_c')
    assert available(shared, shared['c']).json()['total'] == 1
    # Cross-project source access remains forbidden even for workspace-wide metadata sharing.
    assert client.get('/api/inputs/'+item['record_id'],params={'space_id':shared['scenes'][0]['id']}).status_code == 403


def test_unknown_historical_version_is_not_reconstructed_and_stale_grant_fails(shared):
    client = shared['client']
    store = SceneAttachments(shared['jobs'].inputs)
    path = store.root/shared['scenes'][0]['id']/shared['attachment']['id']/'record.json'
    record = json.loads(path.read_bytes());record['name']='changed-before-first-share.txt';path.write_text(json.dumps(record))
    item = shared['item']
    result = change(client,shared['headers'],'grant',resource_id=item['resource_id'],version_id=item['source_version']['version_id'],
                    expected_resource_revision=1,target_project_id=shared['b'])
    assert result.status_code == 409 and result.json()['detail'] == 'resource_version_unavailable'
    updated=next(i for i in client.get('/api/data-resources').json()['items'] if i['kind']=='attachment')
    assert register(client,shared['headers'],updated,shared['a'],request_id=uuid4().hex).status_code==200
    shared['item']=updated|{'revision':2}
    response=change(client,shared['headers'],'grant',resource_id=item['resource_id'],version_id=updated['source_version']['version_id'],
                    expected_resource_revision=2,target_project_id=shared['b'])
    granted=response.json()['after']
    assert change(client,shared['headers'],'revoke',grant_id=granted['id'],expected_revision=1).status_code==200
    renewed=change(client,shared['headers'],'grant',resource_id=item['resource_id'],version_id=updated['source_version']['version_id'],
                    expected_resource_revision=2,target_project_id=shared['b'],expected_revision=2).json()['after']
    headers,_=sign_in(shared['secured'],'usr_other')
    assert use(shared,headers,granted).json()['detail']=='resource_sharing_revision_changed'
    assert use(shared,headers,renewed).status_code==200
