"""Workspace-wide archive blockers and serialized new-use exclusion."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from uuid import uuid4

import pytest

from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_resource_files import upload, file_item, download
from test_resource_sharing import shared, change, grant, use
from test_resource_versions import append
from test_workspace_resources import register


def report(client, identity):
    return client.get('/api/data-governance', params={'resource_id': identity})


def command(client, headers, identity, action='archive', **values):
    r = report(client, identity)
    assert r.status_code == 200, r.text
    body = {'resource_id': identity, 'action': action, 'request_id': uuid4().hex,
            'expected_revision': r.json()['revision'], 'expected_snapshot': r.json()['snapshot'],
            'reason': 'Synthetic archive validation'} | values
    return body, client.post('/api/data-governance', headers=headers, json=body)


def test_recoverable_archive_keeps_original_history_and_blocks_all_new_mutations(secured):
    _, client, _, _, jobs, directory, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers, payload=b'OLD').json()['resource_id']
    old = file_item(client, identity)
    assert append(client, headers, old, payload=b'NEW').status_code == 201
    item = file_item(client, identity)
    available_count = client.get('/api/data-resources', params={'lifecycle': 'active'}).json()['total']
    before = {p: p.read_bytes() for p in jobs.root.rglob('*') if p.is_file()}
    r = report(client, identity)
    assert r.status_code == 200, r.text
    assert r.json()['impact'] == {'scope': 'workspace', 'has_linked_references': False, 'has_active_grants': False}
    assert r.headers['cache-control'] == 'no-store'
    body, response = command(client, headers, identity)
    assert response.status_code == 200, response.text
    assert client.post('/api/data-governance', headers=headers, json=body).json()['replayed']
    assert client.post('/api/data-governance', headers=headers, json=body | {'reason': 'changed'}).status_code == 409
    assert file_item(client, identity)['lifecycle_state'] == 'archived'
    assert client.get('/api/data-resources', params={'lifecycle': 'active'}).json()['total'] == available_count - 1
    archived = client.get('/api/data-resources', params={'lifecycle': 'archived'}).json()
    assert [v['resource_id'] for v in archived['items']] == [identity]
    assert append(client, headers, item).json()['detail'] == 'resource_archived'
    assert register(client, headers, item, None, owner_kind='workspace', request_id=uuid4().hex).json()['detail'] == 'resource_archived'
    response = change(client, headers, 'grant', resource_id=identity, version_id=item['source_version']['version_id'],
                      expected_resource_revision=item['revision'], target_kind='workspace')
    assert response.json()['detail'] == 'resource_archived'
    assert download(client, old).content == b'OLD'
    assert download(client, item).content == b'NEW'
    assert command(client, headers, identity, 'restore')[1].status_code == 200
    assert append(client, headers, item).status_code == 201
    assert file_item(client, identity)['lifecycle_state'] == 'active'
    assert before == {p: p.read_bytes() for p in jobs.root.rglob('*') if p.is_file()}
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM data_governance_changes').fetchone()[0] == 2


def test_active_grants_and_invisible_or_revoked_references_block_archive(shared):
    s = shared
    identity = upload(s['client'], s['headers'], s['a']).json()['resource_id']
    s['item'] = file_item(s['client'], identity)
    granted = grant(s)
    r = report(s['client'], identity).json()
    assert r['impact']['has_active_grants'] is True
    assert command(s['client'], s['headers'], identity)[1].json()['detail'] == 'resource_has_active_grants'
    headers, _ = sign_in(s['secured'], 'usr_other')
    used = use(s, headers, granted, space_id=s['scenes'][1]['id']).json()['after']
    s['headers'], _ = sign_in(s['secured'], 'usr_manager')
    # Source manager cannot inspect the receiving scene, but the global guard must see it.
    assert s['client'].get('/api/data-lineage', params={'resource_id': identity}).json()['total'] == 0
    impact = report(s['client'], identity).json()['impact']
    assert impact['has_linked_references'] is True
    assert 'linked_references' not in impact
    assert s['scenes'][1]['id'] not in report(s['client'], identity).text
    assert change(s['client'], s['headers'], 'revoke', grant_id=granted['id'], expected_revision=1).status_code == 200
    assert command(s['client'], s['headers'], identity)[1].json()['detail'] == 'resource_has_references'
    headers, _ = sign_in(s['secured'], 'usr_other')
    assert change(s['client'], headers, 'unlink', use_id=used['id'], expected_revision=1).status_code == 200
    s['headers'], _ = sign_in(s['secured'], 'usr_manager')
    assert command(s['client'], s['headers'], identity)[1].status_code == 200
    assert use(s, s['headers'], granted).status_code in (403, 409)


def test_stale_impact_and_scope_csrf_checks(secured):
    _, client, accounts, _, _, _, scenes, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']
    r = report(client, identity).json()
    item = file_item(client, identity)
    assert append(client, headers, item).status_code == 201
    body = {'resource_id': identity, 'action': 'archive', 'request_id': uuid4().hex,
            'expected_revision': r['revision'], 'expected_snapshot': r['snapshot'], 'reason': 'Stale check'}
    assert client.post('/api/data-governance', json=body, headers=headers).json()['detail'] == 'resource_governance_changed'
    assert client.post('/api/data-governance', json=body).status_code == 403
    for extra in ({'project_id': 'project-'+'a'*16}, {'action': 'delete'}):
        assert client.post('/api/data-governance', json=body | extra, headers=headers).status_code == 422
    sign_in(secured, 'usr_engineer')
    assert report(client, identity).status_code == 403
    accounts.workspace = 'other'; accounts.roles = ['workspace:owner']; sign_in(secured, 'usr_owner')
    assert report(client, identity).status_code == 403
    accounts.workspace = 'ws_mock'; accounts.roles = ['workspace:member']; headers, _ = sign_in(secured, 'usr_manager')
    from test_workspace_projects import create
    project = create(client, headers)['project_id']
    source = next(i for i in client.get('/api/data-resources').json()['items'] if i['kind'] == 'input')
    assert register(client, headers, source, project).status_code == 200
    assert report(client, source['resource_id']).json()['detail'] == 'resource_scene_lifecycle_required'


@pytest.mark.parametrize('table', ['data_resource_states', 'data_resource_grants', 'data_resource_uses'])
def test_corrupt_state_or_hidden_relationship_fails_closed(secured, table):
    _, client, _, _, _, directory, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']
    item = file_item(client, identity)
    assert command(client, headers, identity)[1].status_code == 200
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        db.execute(f'CREATE TABLE IF NOT EXISTS {table}(scope TEXT,id TEXT,record TEXT NOT NULL,PRIMARY KEY(scope,id))')
        scope = db.execute('SELECT scope FROM data_resources').fetchone()[0]
        db.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?,?)', (scope, identity, '{}'))
    assert report(client, identity).status_code == 503
    if table == 'data_resource_states':
        assert append(client, headers, item).status_code == 503


@pytest.mark.parametrize('mutation', ['grant', 'append', 'register'])
def test_archive_racing_new_use_never_commits_both(secured, mutation):
    _, client, _, _, _, directory, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']; item = file_item(client, identity)
    r = report(client, identity).json()
    archive = {'resource_id': identity, 'action': 'archive', 'request_id': uuid4().hex,
               'expected_revision': r['revision'], 'expected_snapshot': r['snapshot'], 'reason': 'Race'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, '/api/data-governance', json=archive, headers=headers)
        if mutation == 'grant':
            second = pool.submit(change, client, headers, 'grant', resource_id=identity,
                                 version_id=item['source_version']['version_id'], expected_resource_revision=1, target_kind='workspace')
        elif mutation == 'append':
            second = pool.submit(append, client, headers, item)
        else:
            second = pool.submit(register, client, headers, item, None, owner_kind='workspace', request_id=uuid4().hex)
        responses = [first.result(), second.result()]
    assert sum(r.status_code in (200, 201) for r in responses) == 1
    assert sum(r.status_code == 409 for r in responses) == 1
    final = report(client, identity).json()
    assert not (final['state'] == 'archived' and final['impact']['has_active_grants'])


def test_expired_unreferenced_grant_does_not_block_archive_but_cannot_be_reused(secured):
    _, client, _, _, _, directory, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']; item = file_item(client, identity)
    granted = change(client, headers, 'grant', resource_id=identity, version_id=item['source_version']['version_id'],
                     expected_resource_revision=1, target_kind='workspace').json()['after']
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        raw = json.loads(db.execute('SELECT record FROM data_resource_grants WHERE id=?', (granted['id'],)).fetchone()[0])
        raw['expires_at'] = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        db.execute('UPDATE data_resource_grants SET record=? WHERE id=?', (json.dumps(raw), granted['id']))
    assert command(client, headers, identity)[1].status_code == 200
    assert report(client, identity).json()['impact']['has_active_grants'] is False
