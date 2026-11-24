"""Original history and explicit upgrades stay authorized, atomic and immutable."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from uuid import uuid4

import pytest

from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_resource_files import upload, file_item, download
from test_resource_sharing import shared, grant, use, change
from test_workspace_projects import create, associate


def append(client, headers, item, payload=b'SYNTHETIC UPDATED SURVEY', **values):
    params = {'resource_id': item['resource_id'], 'expected_version': item['source_version']['version_id'],
              'expected_revision': str(item['revision']), 'name': 'survey-v2.csv',
              'request_id': uuid4().hex, 'reason': 'Append synthetic survey original'} | values
    return client.post('/api/data-files/versions', params=params, content=payload,
                       headers={'Content-Type': 'application/octet-stream'} | headers)


@pytest.fixture
def versioned(shared):
    s = shared
    response = upload(s['client'], s['headers'], s['a'], payload=b'ORIGINAL SURVEY')
    assert response.status_code == 201, response.text
    s['item'] = file_item(s['client'], response.json()['resource_id'])
    s['old_grant'] = grant(s)
    headers, _ = sign_in(s['secured'], 'usr_other')
    response = use(s, headers, s['old_grant'], space_id=s['scenes'][1]['id'])
    assert response.status_code == 200, response.text
    s['use'] = response.json()['after']
    s['headers'], _ = sign_in(s['secured'], 'usr_manager')
    response = append(s['client'], s['headers'], s['item'])
    assert response.status_code == 201, response.text
    s['new_item'] = file_item(s['client'], s['item']['resource_id'])
    response = change(s['client'], s['headers'], 'grant', resource_id=s['item']['resource_id'],
                      version_id=s['new_item']['source_version']['version_id'], expected_resource_revision=2,
                      target_project_id=s['b'], allow_download=True)
    assert response.status_code == 200, response.text
    s['new_grant'] = response.json()['after']
    return s


def compare(s, **values):
    return s['client'].get('/api/data-reference-upgrade', params={'use_id': s['use']['id']} | values)


def upgrade(s, headers, **values):
    return change(s['client'], headers, 'upgrade', use_id=s['use']['id'], grant_id=s['new_grant']['id'],
                  expected_grant_revision=s['new_grant']['revision'], expected_version=s['use']['version_id'],
                  expected_revision=s['use']['revision'], **values)


def test_append_retains_all_originals_registration_storage_and_checkpoint(secured, tmp_path):
    from packages.data.resource_storage_usage import stored_bytes
    from test_ontology_deployment_checkpoint import module
    _, client, _, _, jobs, directory, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers, payload=b'OLD').json()['resource_id']
    old = file_item(client, identity)
    source_before = {p: p.read_bytes() for p in jobs.inputs.root.rglob('*') if p.is_file()}
    response = append(client, headers, old, payload=b'NEW DATA')
    assert response.status_code == 201, response.text
    current = file_item(client, identity)
    assert current['version_count'] == current['revision'] == 2
    assert current['owner_kind'] == old['owner_kind'] == 'workspace'
    assert current['is_base'] == old['is_base']
    assert download(client, old).content == b'OLD'
    assert download(client, current).content == b'NEW DATA'
    assert sum(stored_bytes(directory, []).values()) == 11
    trace = client.get('/api/data-lineage', params={'resource_id': identity}).json()
    assert len(trace['versions']) == 2
    assert sum(v['current'] for v in trace['versions']) == 1
    assert source_before == {p: p.read_bytes() for p in jobs.inputs.root.rglob('*') if p.is_file()}
    root = tmp_path/'history-checkpoint'; target = root/'data/business/runtime/preview-directory'
    target.mkdir(parents=True)
    source = directory.root/'business-projects.sqlite3'
    with sqlite3.connect(source) as original, sqlite3.connect(target/source.name) as db:
        original.backup(db)
    checkpoint = module.checkpoint(root, [])
    with sqlite3.connect(checkpoint/source.name) as db:
        assert db.execute('SELECT payload FROM data_resource_file_history').fetchone()[0] == b'OLD'
        assert db.execute('SELECT payload FROM data_resource_files').fetchone()[0] == b'NEW DATA'


def test_historical_original_can_be_shared_for_the_first_time(secured):
    _, client, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    project = create(client, headers)['project_id']
    identity = upload(client, headers, payload=b'OLD').json()['resource_id']
    old = file_item(client, identity)
    assert append(client, headers, old).status_code == 201
    response = change(client, headers, 'grant', resource_id=identity,
                      version_id=old['source_version']['version_id'], expected_resource_revision=2,
                      target_project_id=project, allow_download=True)
    assert response.status_code == 200, response.text
    g = response.json()['after']
    result = client.get('/api/data-sharing/download', params={'grant_id': g['id'], 'project_id': project, 'grant_revision': 1})
    assert result.status_code == 200
    assert result.content == b'OLD'


def test_append_idempotence_conflicts_and_history_budget(secured, monkeypatch):
    from packages.data import resource_files
    _, client, _, _, _, directory, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers, payload=b'123').json()['resource_id']
    old = file_item(client, identity); request = uuid4().hex
    assert append(client, headers, old, payload=b'45', request_id=request).status_code == 201
    replay = append(client, headers, old, payload=b'45', request_id=request)
    assert replay.status_code == 200
    assert replay.json()['replayed'] is True
    assert append(client, headers, old, payload=b'changed', request_id=request).status_code == 409
    assert append(client, headers, old).status_code == 409
    current = file_item(client, identity)
    monkeypatch.setattr(resource_files, 'MAX_STORED_BYTES', 6)
    assert append(client, headers, current, payload=b'67').status_code == 409
    monkeypatch.setattr(resource_files, 'MAX_STORED_BYTES', 512*1024*1024)
    monkeypatch.setattr(resource_files, 'MAX_FILES', 2)
    assert append(client, headers, current, payload=b'6').status_code == 409
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM data_resource_file_history').fetchone()[0] == 1


def test_concurrent_appends_only_accept_one_expected_revision(secured):
    _, client, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']; old = file_item(client, identity)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: append(client, headers, old), range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert file_item(client, identity)['version_count'] == 2


@pytest.mark.parametrize('values', [{'owner_kind': 'workspace'}, {'space_id': 'space-'+'a'*16},
                                  {'name': '../bad.csv'}, {'expected_revision': '0'}, {'expected_version': 'invalid'}])
def test_append_rejects_ownership_injection_and_invalid_metadata(secured, values):
    _, client, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']; old = file_item(client, identity)
    assert append(client, headers, old, **values).status_code == 422
    assert file_item(client, identity)['version_count'] == 1


def test_append_streaming_rechecks_rights_before_commit(secured):
    from packages.service.space_access import SpaceAccessPolicy
    _, client, _, _, _, directory, _, policies, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']; old = file_item(client, identity)
    def revoked():
        yield b'new'
        revision, _ = policies.load()
        policies.replace(SpaceAccessPolicy(bindings=[], grants=[]), expected_revision=revision, actor='test', reason='Revoke append')
        yield b'data'
    assert append(client, headers, old, payload=revoked()).status_code == 403
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM data_resource_file_history').fetchone()[0] == 0


def test_compare_and_upgrade_preserve_use_identity_and_frozen_old_access(versioned):
    s = versioned; client = s['client']
    # Publishing the new original and grant alone never changes a consumer.
    headers, _ = sign_in(s['secured'], 'usr_other')
    before = client.get('/api/data-sharing', params={'view': 'uses', 'project_id': s['b']}).json()['items'][0]
    assert before['version_id'] == s['item']['source_version']['version_id']
    result = compare(s)
    assert result.status_code == 200, result.text
    report = result.json()
    assert len(report['candidates']) == 1
    assert s['scenes'][0]['id'] not in result.text
    assert s['scenes'][1]['id'] in result.text
    assert client.get('/api/data-files/download', params={'resource_id': s['item']['resource_id'],
                      'version_id': s['new_grant']['version_id']}).status_code == 403
    request = uuid4().hex
    response = upgrade(s, headers, request_id=request)
    assert response.status_code == 200, response.text
    saved = response.json()['after']
    for field in ('id', 'project_id', 'space_id', 'purpose', 'resource_id', 'coordinate_status', 'use_mode'):
        assert saved[field] == s['use'][field]
    assert saved['version_id'] == s['new_grant']['version_id']
    assert saved['revision'] == 2
    assert response.json()['before'] == s['use']
    assert upgrade(s, headers, request_id=request).json()['replayed'] is True
    assert upgrade(s, headers).status_code == 409
    assert client.get('/api/data-sharing/download', params={'grant_id': s['old_grant']['id'],
                      'project_id': s['b'], 'grant_revision': 1}).content == b'ORIGINAL SURVEY'
    assert client.get('/api/data-sharing/download', params={'grant_id': s['new_grant']['id'],
                      'project_id': s['b'], 'grant_revision': 1}).content == b'SYNTHETIC UPDATED SURVEY'
    assert client.get('/api/spaces/'+s['scenes'][0]['id']).status_code == 403
    assert compare(s).json()['current']['source_version']['version_id'] == saved['version_id']


def test_upgrade_rejects_wrong_project_grant_and_unseen_reference(versioned):
    s = versioned
    headers, _ = sign_in(s['secured'], 'usr_c')
    assert compare(s).status_code == 403
    assert upgrade(s, headers).status_code == 403
    headers, _ = sign_in(s['secured'], 'usr_manager')
    response = change(s['client'], headers, 'grant', resource_id=s['new_item']['resource_id'],
                      version_id=s['new_grant']['version_id'], expected_resource_revision=2, target_project_id=s['c'])
    assert response.status_code == 200
    foreign = response.json()['after']
    headers, _ = sign_in(s['secured'], 'usr_other')
    with_grant = s | {'new_grant': foreign}
    assert upgrade(with_grant, headers).status_code == 403
    assert compare(s, project_id=s['c']).status_code == 422
    assert s['client'].post('/api/data-reference-upgrade', headers=headers, json={}).status_code == 403


def test_revoked_old_grant_can_upgrade_but_revoked_new_grant_cannot(versioned):
    s = versioned
    assert change(s['client'], s['headers'], 'revoke', grant_id=s['old_grant']['id'], expected_revision=1).status_code == 200
    headers, _ = sign_in(s['secured'], 'usr_other')
    assert upgrade(s, headers).status_code == 200
    manager, _ = sign_in(s['secured'], 'usr_manager')
    assert change(s['client'], manager, 'revoke', grant_id=s['new_grant']['id'], expected_revision=1).status_code == 200
    headers, _ = sign_in(s['secured'], 'usr_other')
    assert compare(s).json()['total'] == 0
    assert upgrade(s, headers).status_code == 403


def test_upgrade_failure_and_tampered_snapshot_leave_reference_untouched(versioned):
    s = versioned
    with sqlite3.connect(s['directory'].root/'business-projects.sqlite3') as db:
        db.execute('UPDATE data_shared_versions SET record=? WHERE version_id=?', ('{}', s['new_grant']['version_id']))
    headers, _ = sign_in(s['secured'], 'usr_other')
    assert compare(s).status_code == 503
    assert upgrade(s, headers).status_code == 503
    with sqlite3.connect(s['directory'].root/'business-projects.sqlite3') as db:
        record = json.loads(db.execute('SELECT record FROM data_resource_uses WHERE id=?', (s['use']['id'],)).fetchone()[0])
        assert record == s['use']


def test_concurrent_upgrades_one_wins_and_replay_still_requires_current_access(versioned):
    s = versioned
    headers, _ = sign_in(s['secured'], 'usr_other')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: upgrade(s, headers), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    manager, _ = sign_in(s['secured'], 'usr_manager')
    assert change(s['client'], manager, 'revoke', grant_id=s['new_grant']['id'], expected_revision=1).status_code == 200
    headers, _ = sign_in(s['secured'], 'usr_other')
    assert upgrade(s, headers).status_code == 403


def test_legacy_originals_read_without_history_table_and_corruption_is_unavailable(secured):
    _, client, _, _, _, directory, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']; old = file_item(client, identity)
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        db.execute('DROP TABLE data_resource_file_history')
    assert download(client, old).status_code == 200
    assert append(client, headers, old).status_code == 201
    with sqlite3.connect(directory.root/'business-projects.sqlite3') as db:
        db.execute("UPDATE data_resource_file_history SET record='{}'")
    assert download(client, old).status_code == 503


def test_expired_and_cross_resource_candidates_are_not_upgrade_authority(versioned):
    s = versioned
    # Another original with a valid B grant must never replace this reference.
    identity = upload(s['client'], s['headers'], s['a']).json()['resource_id']
    other = file_item(s['client'], identity)
    response = change(s['client'], s['headers'], 'grant', resource_id=identity,
                      version_id=other['source_version']['version_id'], expected_resource_revision=1, target_project_id=s['b'])
    assert response.status_code == 200
    foreign = response.json()['after']
    with sqlite3.connect(s['directory'].root/'business-projects.sqlite3') as db:
        record = s['new_grant'] | {'expires_at': (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()}
        db.execute('UPDATE data_resource_grants SET record=? WHERE id=?', (json.dumps(record), record['id']))
    headers, _ = sign_in(s['secured'], 'usr_other')
    assert compare(s).json()['total'] == 0
    assert upgrade(s, headers).status_code == 403
    assert upgrade(s | {'new_grant': foreign}, headers).status_code == 403


def test_append_requires_current_manager_even_for_exact_retry(secured):
    _, client, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']; old = file_item(client, identity)
    request = uuid4().hex
    assert append(client, headers, old, request_id=request).status_code == 201
    member, _ = sign_in(secured, 'usr_engineer')
    assert append(client, member, old, request_id=request).status_code == 403
