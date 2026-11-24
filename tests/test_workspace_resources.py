from dataclasses import replace
import json

import pytest

from packages.data.workspace_resources import ResourceQuery, WorkspaceResources
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_workspace_projects import create, associate


def register(client, headers, item, project, **values):
    return client.post('/api/data-resources', headers=headers, json={
        'resource_id': item['resource_id'], 'request_id': 'e'*32,
        'expected_revision': item['revision'], 'expected_version': item['source_version']['version_id'],
        'owner_project_id': project, 'is_base': True, 'reason': 'Confirmed resource registration'} | values)


def test_resources_exclude_process_and_uncreated_exports_and_read_without_writes(secured):
    _, client, _, _, jobs, directory, _, *_ = secured
    sign_in(secured, 'usr_engineer')
    before = {p: p.read_bytes() for p in jobs.root.parent.rglob('*') if p.is_file()}
    response = client.get('/api/data-resources')
    assert response.status_code == 200, response.text
    report = response.json()
    assert {i['kind'] for i in report['items']} == {'input', 'candidate', 'human_view', 'agent_view'}
    assert all(not i['registered'] and i['owner_project_id'] is None for i in report['items'])
    assert all(len(i['source_version']['version_id']) == 64 for i in report['items'])
    assert report['source_files_rechecked'] is False
    assert before == {p: p.read_bytes() for p in jobs.root.parent.rglob('*') if p.is_file()}
    process = client.get('/api/data-resources', params={'category': 'process'}).json()
    assert process['items'] and all(i['kind'] in ('job', 'batch', 'preflight') for i in process['items'])
    assert not (directory.root / 'business-projects.sqlite3').exists()
    assert client.get('/api/data-catalog').json()['profile'] == 'cospace.workspace-data-catalog/0.1'


def test_registration_ownership_survives_scene_reassociation_and_restart(secured):
    rp, client, accounts, _, jobs, directory, scenes, policies, *_ = secured
    accounts.roles = ['workspace:owner']
    headers, _ = sign_in(secured, 'usr_owner')
    a = create(client, headers)['project_id']
    b = create(client, headers, 1, 'b', name='Inspection')['project_id']
    associate(client, headers, scenes[0]['id'], a, 2, 'c')
    item = next(i for i in client.get('/api/data-resources').json()['items'] if i['kind'] == 'input')
    before = {p: p.read_bytes() for p in jobs.root.parent.rglob('*.json')}
    saved = register(client, headers, item, a)
    assert saved.status_code == 200, saved.text
    assert register(client, headers, item, a).json()['replayed'] is True
    associate(client, headers, scenes[0]['id'], b, 3, 'd')
    for project in (a, b):
        result = client.get('/api/data-resources', params={'project_id': project}).json()
        row = next(i for i in result['items'] if i['resource_id'] == item['resource_id'])
        assert row['owner_project_id'] == a and row['project_id'] == b
        assert row['registered'] and row['is_base'] and row['version_count'] == 1
    assert before == {p: p.read_bytes() for p in jobs.root.parent.rglob('*.json')}
    assert directory.read('space', scenes[0]['id'])['project_id'] == scenes[0]['project_id']
    assert client.get('/api/data-resources', params={'category': 'base'}).json()['total'] == 1
    assert register(client, headers, item | {'revision': 1}, b, request_id='f'*32).json()['detail'] == 'resource_owner_transfer_not_supported'
    _, policy = policies.load()
    from test_space_access import principal
    user = replace(principal(), issuer=rp.config.issuer, org_id='org_mock', workspace_id='ws_mock',
                   subject='usr_owner', governance_roles=('workspace:owner',))
    assert any(i['registered'] for i in WorkspaceResources(jobs, directory).read(user, policy, ResourceQuery())['items'])


def test_version_snapshot_change_requires_explicit_registration_and_keeps_history(secured):
    _, client, _, _, jobs, _, _, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    project = create(client, headers)['project_id']
    item = next(i for i in client.get('/api/data-resources').json()['items'] if i['kind'] == 'candidate')
    assert register(client, headers, item, project).status_code == 200
    path = jobs.root / item['record_id'] / 'output/model.json'
    value = json.loads(path.read_bytes()); value['note'] = 'Changed metadata fixture'
    path.write_text(json.dumps(value))
    changed = next(i for i in client.get('/api/data-resources').json()['items'] if i['resource_id'] == item['resource_id'])
    assert not changed['version_registered'] and changed['version_count'] == 1
    stale = register(client, headers, item | {'revision': 1}, project, request_id='f'*32)
    assert stale.status_code == 409 and stale.json()['detail'] == 'resource_source_changed'
    assert register(client, headers, changed, project, request_id='f'*32).status_code == 200
    row = next(i for i in client.get('/api/data-resources').json()['items'] if i['resource_id'] == item['resource_id'])
    assert row['version_count'] == 2 and row['version_registered']


def test_project_archive_checks_resource_ownership_in_same_transaction(secured):
    _, client, _, _, _, _, _, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    project = create(client, headers)['project_id']
    item = client.get('/api/data-resources').json()['items'][0]
    assert register(client, headers, item, project).status_code == 200
    response = client.post('/api/data-projects', headers=headers, json={'action': 'update', 'project_id': project,
        'name': 'Archived', 'status': 'archived', 'request_id': 'f'*32, 'expected_revision': 1, 'reason': 'Archive'})
    assert response.status_code == 409 and response.json()['detail'] == 'project_has_managed_resources'


def test_unavailable_models_are_not_counted_as_assets(secured):
    _, client, _, _, jobs, _, _, *_ = secured
    sign_in(secured, 'usr_engineer')
    (jobs.root / 'build-one/output/model.json').write_text('{}')
    data = client.get('/api/data-resources').json()
    assert data['status'] == 'partial'
    assert not any(i['record_id'] == 'build-one' for i in data['items'])


def test_scope_filters_and_parameter_forgery_fail_closed(secured):
    _, client, accounts, _, _, _, scenes, *_ = secured
    assert client.get('/api/data-resources').status_code == 401
    headers, _ = sign_in(secured, 'usr_manager')
    project = create(client, headers)['project_id']
    item = client.get('/api/data-resources').json()['items'][0]
    assert register(client, {}, item, project).status_code == 403
    for invalid in ({'owner_project_id': 'project-'+'f'*16}, {'expected_version': 'f'*64}, {'expected_revision': 5}):
        assert register(client, headers, item, project, **invalid).status_code == 409
    assert register(client, headers, item, project, actor='usr_owner').status_code == 422
    assert client.get('/api/data-resources', params={'workspace_id': 'foreign'}).status_code == 422
    assert client.get('/api/data-resources', params={'space_id': scenes[1]['id']}).status_code == 403
    assert client.get('/api/data-resources', params={'project_id': 'project-'+'f'*16}).status_code == 403
    sign_in(secured, 'usr_other')
    assert all(i['space_id'] == scenes[1]['id'] for i in client.get('/api/data-resources').json()['items'])
    accounts.workspace = 'foreign'; sign_in(secured, 'usr_owner')
    assert client.get('/api/data-resources').json()['items'] == []


def test_reference_assets_pagination_and_search(secured):
    from packages.data.scene_attachments import SceneAttachments
    _, client, _, _, jobs, _, scenes, *_ = secured
    sign_in(secured, 'usr_engineer')
    path = jobs.inputs.root / 'fixture.txt'; path.write_text('synthetic control network')
    SceneAttachments(jobs.inputs).register(path, scenes[0]['id'], 'control-network.txt', 'usr_test')
    data = client.get('/api/data-resources', params={'category': 'reference'}).json()
    assert data['total'] == 1 and data['items'][0]['source_version']['bytes'] == path.stat().st_size
    assert client.get('/api/data-resources', params={'search': 'control-network'}).json()['total'] == 1
    page = client.get('/api/data-resources', params={'limit': 1}).json()
    assert len(page['items']) == 1 and page['next_offset'] == 1 and page['total'] > 1


def test_existing_pointcloud_is_a_result_and_invalid_metadata_is_partial(secured):
    _, client, _, _, jobs, _, _, *_ = secured
    sign_in(secured, 'usr_engineer')
    item = next(i for i in client.get('/api/data-resources').json()['items'] if i['kind'] == 'input')
    path = jobs.inputs.root / (item['record_id'] + '.json')
    value = json.loads(path.read_bytes()); value['format'] = 'ply_pointcloud'
    path.write_text(json.dumps(value))
    result = client.get('/api/data-resources', params={'category': 'result'}).json()
    assert any(i['kind'] == 'input' for i in result['items'])
    assert not client.get('/api/data-resources', params={'category': 'acquisition'}).json()['items']
    value['format'] = {'corrupt': True}; path.write_text(json.dumps(value))
    invalid = client.get('/api/data-resources').json()
    assert invalid['status'] == 'partial' and not any(i['kind'] == 'input' for i in invalid['items'])


def test_readable_resource_owner_remains_selectable_without_current_scene_link(secured):
    _, client, _, _, _, _, scenes, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    a = create(client, headers)['project_id']
    b = create(client, headers, 1, 'b', name='Park operations')['project_id']
    item = client.get('/api/data-resources').json()['items'][0]
    assert register(client, headers, item, a).status_code == 200
    assert associate(client, headers, scenes[0]['id'], b, 2, 'c').status_code == 200
    sign_in(secured, 'usr_engineer')
    assert {v['id'] for v in client.get('/api/data-projects').json()['items']} == {a, b}
    data = client.get('/api/data-resources', params={'project_id': a}).json()
    assert data['total'] == 1 and not data['can_manage']
    assert not data['items'][0]['can_manage']
