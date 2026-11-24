"""Trace is read-only and must not widen source or project access."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_resource_sharing import shared, grant, use, change
from test_resource_files import upload


def trace(shared, **values):
    return shared['client'].get('/api/data-lineage', params={'resource_id': shared['item']['resource_id']} | values)


def test_source_trace_reports_registered_versions_and_only_visible_uses_without_writes(shared):
    client = shared['client']
    granted = grant(shared)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert use(shared, headers, granted).status_code == 200
    sign_in(shared['secured'], 'usr_manager')
    before = {p: p.read_bytes() for p in shared['directory'].root.rglob('*') if p.is_file()}
    response = trace(shared)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['view'] == 'source'
    assert report['source']['state'] == 'current'
    assert report['source']['version_id'] == granted['version_id']
    assert report['versions'][0]['snapshot_saved'] is True
    # The manager can manage the source, but cannot view the receiving scene.
    # A project-level use remains visible to this workspace manager.
    assert report['total'] == 1
    assert report['references'][0]['project_id'] == shared['b']
    assert report['summary']['linked_references'] == 1
    assert report['summary']['scope'] == 'visible_only'
    assert report['impact']['global_assessment'] == 'not_assessed'
    assert report['impact']['physical_delete_supported'] is False
    assert report['source_files_rechecked'] is False
    assert 'no-store' in response.headers['cache-control']
    assert before == {p: p.read_bytes() for p in shared['directory'].root.rglob('*') if p.is_file()}
    assert client.head('/api/data-lineage', params={'resource_id': report['resource_id']}).status_code == 200


def test_reference_trace_keeps_source_and_other_projects_private_even_after_revocation(shared):
    granted = grant(shared)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert use(shared, headers, granted).status_code == 200
    denied = trace(shared)
    assert denied.status_code == 403
    response = trace(shared, project_id=shared['b'])
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['source'] == {'state': 'restricted', 'version_id': None, 'space_name': None, 'href': None}
    assert report['versions'][0]['current'] is None
    assert report['versions'][0]['recorded_at'] is None
    assert shared['scenes'][0]['id'] not in response.text
    assert shared['attachment']['id'] not in response.text
    assert shared['c'] not in response.text
    assert shared['jobs'].root.as_posix() not in response.text
    assert trace(shared, project_id=shared['c']).status_code == 403
    owner_headers, _ = sign_in(shared['secured'], 'usr_manager')
    assert change(shared['client'], owner_headers, 'revoke', grant_id=granted['id'], expected_revision=1).status_code == 200
    sign_in(shared['secured'], 'usr_other')
    report = trace(shared, project_id=shared['b']).json()
    assert report['references'][0]['access_status'] == 'revoked'
    assert report['summary']['effective_references'] == 0
    assert report['impact']['retention_required'] is True


def test_source_metadata_change_does_not_upgrade_reference_or_expose_new_version(shared):
    granted = grant(shared)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert use(shared, headers, granted).status_code == 200
    old = granted['version_id']
    # Use the same verified metadata location as the attachment store.
    path = next(p for p in shared['jobs'].inputs.root.rglob('*.json') if shared['attachment']['id'] == json.loads(p.read_bytes()).get('id'))
    value = json.loads(path.read_bytes())
    value['actor'] = 'Changed source metadata'
    path.write_text(json.dumps(value))
    sign_in(shared['secured'], 'usr_manager')
    owner = trace(shared).json()
    assert owner['source']['version_id'] != old
    assert [v['version_id'] for v in owner['versions']] == [old]
    assert owner['references'][0]['version_id'] == old
    sign_in(shared['secured'], 'usr_other')
    consumer = trace(shared, project_id=shared['b']).json()
    assert [v['version_id'] for v in consumer['versions']] == [old]


def test_source_missing_is_partial_not_empty_and_preserves_registered_versions(shared):
    granted = grant(shared)
    # A readable snapshot remains evidence of a version, not a recovered source.
    for path in shared['jobs'].inputs.root.rglob('*.json'):
        if json.loads(path.read_bytes()).get('id') == shared['attachment']['id']:
            path.unlink()
    result = trace(shared)
    assert result.status_code == 200, result.text
    report = result.json()
    assert report['status'] == 'partial'
    assert report['source']['state'] == 'unavailable'
    assert report['versions'][0]['version_id'] == granted['version_id']
    assert report['versions'][0]['current'] is None


def test_trace_filters_invisible_scene_uses_and_counts_after_filtering(shared):
    granted = grant(shared)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert use(shared, headers, granted, space_id=shared['scenes'][1]['id']).status_code == 200
    sign_in(shared['secured'], 'usr_manager')
    source = trace(shared).json()
    assert source['total'] == 0
    assert source['summary']['projects'] == 0
    assert source['impact']['global_assessment'] == 'not_assessed'
    assert shared['scenes'][1]['id'] not in json.dumps(source)
    sign_in(shared['secured'], 'usr_other')
    assert trace(shared, project_id=shared['b']).json()['total'] == 1


def test_trace_pagination_and_unlink_retention(shared):
    granted = grant(shared, expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    headers, _ = sign_in(shared['secured'], 'usr_other')
    first = use(shared, headers, granted).json()['after']
    assert use(shared, headers, granted, space_id=shared['scenes'][1]['id']).status_code == 200
    report = trace(shared, project_id=shared['b'], limit=1).json()
    assert report['total'] == 2
    assert len(report['references']) == 1
    assert report['next_offset'] == 1
    assert report['summary']['linked_references'] == 2
    second = trace(shared, project_id=shared['b'], limit=1, offset=1).json()
    assert second['references'][0]['id'] != report['references'][0]['id']
    assert second['next_offset'] is None
    assert change(shared['client'], headers, 'unlink', use_id=first['id'], expected_revision=1).status_code == 200
    report = trace(shared, project_id=shared['b']).json()
    assert report['summary']['historical_references'] == 1
    assert report['summary']['linked_references'] == 1


def test_grant_without_use_does_not_allow_consumer_trace(shared):
    grant(shared)
    sign_in(shared['secured'], 'usr_other')
    assert trace(shared, project_id=shared['b']).status_code == 403


def test_expired_grant_retains_reference_without_effective_access(shared):
    granted = grant(shared)
    headers, _ = sign_in(shared['secured'], 'usr_other')
    assert use(shared, headers, granted).status_code == 200
    with sqlite3.connect(shared['directory'].root / 'business-projects.sqlite3') as db:
        record = json.loads(db.execute('SELECT record FROM data_resource_grants WHERE id=?', (granted['id'],)).fetchone()[0])
        record['expires_at'] = '2020-01-01T00:00:00+00:00'
        db.execute('UPDATE data_resource_grants SET record=? WHERE id=?', (json.dumps(record), granted['id']))
    report = trace(shared, project_id=shared['b']).json()
    assert report['references'][0]['access_status'] == 'expired'
    assert report['references'][0]['allow_download'] is False
    assert report['summary']['linked_references'] == 1
    assert report['summary']['effective_references'] == 0
    assert report['impact']['retention_required'] is True


def test_independent_file_trace_and_corrupt_registration_fail_closed(shared):
    result = upload(shared['client'], shared['headers'])
    assert result.status_code == 201
    identity = result.json()['resource_id']
    response = trace(shared, resource_id=identity)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['resource']['owner'] == '工作区共用'
    assert report['source']['href'] is None
    assert report['source']['space_name'] is None
    with sqlite3.connect(shared['directory'].root / 'business-projects.sqlite3') as db:
        db.execute('UPDATE data_resources SET record=? WHERE id=?', ('{}', identity))
    assert trace(shared, resource_id=identity).status_code == 503


@pytest.mark.parametrize('query', [{'actor':'admin'}, {'workspace_id':'other'}, {'offset':-1}, {'limit':101}, {'resource_id':'invalid'}])
def test_trace_rejects_forged_query(shared, query):
    assert trace(shared, **query).status_code == 422


def test_trace_requires_authentication_and_is_read_only(shared):
    client = shared['client']
    assert trace(shared, resource_id='resource-'+'f'*32).status_code == 403
    assert client.post('/api/data-lineage', headers=shared['headers'], json={}).status_code == 403
    query = [('resource_id', shared['item']['resource_id']), ('resource_id', shared['item']['resource_id'])]
    assert client.get('/api/data-lineage', params=query).status_code == 403
    client.cookies.clear()
    assert trace(shared).status_code == 401
