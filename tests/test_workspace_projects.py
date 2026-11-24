from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from packages.lifecycle.workspace_projects import WorkspaceProjects, ProjectChange, ProjectQuery, ProjectError
from packages.lifecycle.scene_initialization import checksum
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_space_access import principal


def create(client, headers, revision=0, marker='a', **fields):
    response = client.post('/api/data-projects', headers=headers, json={
        'action': 'create', 'name': 'Park survey', 'description': 'Synthetic project',
        'request_id': marker * 32, 'expected_revision': revision, 'reason': 'Synthetic fixture'} | fields)
    assert response.status_code == 200, response.text
    return response.json()


def associate(client, headers, scene, project, revision, marker):
    return client.post('/api/data-projects', headers=headers, json={
        'action': 'associate', 'space_id': scene, 'project_id': project,
        'request_id': marker * 32, 'expected_revision': revision, 'reason': 'Confirmed scene association'})


def test_business_projects_associate_two_scenes_without_mutating_source_ownership(secured):
    _, client, accounts, _, jobs, directory, scenes, *_ = secured
    accounts.roles = ['workspace:owner']
    headers, _ = sign_in(secured, 'usr_owner')
    before = {p: p.read_bytes() for p in directory.root.parent.rglob('*.json')}
    empty = client.get('/api/data-projects').json()
    assert empty['revision'] == 0 and empty['items'] == []
    assert not (directory.root / 'business-projects.sqlite3').exists()
    first = create(client, headers)
    second = create(client, headers, 1, 'b', name='Park inspection')
    a, b = first['project_id'], second['project_id']
    assert a != b
    assert associate(client, headers, scenes[0]['id'], a, 2, 'c').status_code == 200
    assert associate(client, headers, scenes[1]['id'], b, 3, 'd').status_code == 200
    for identity, scene in ((a, scenes[0]), (b, scenes[1])):
        data = client.get('/api/data-projects', params={'view': 'scenes', 'project_id': identity}).json()
        assert [s['space_id'] for s in data['items']] == [scene['id']]
        assert data['items'][0]['origin_project_id'] == scene['project_id']
        assert directory.read('space', scene['id'])['project_id'] == scene['project_id']
    assert all(p.read_bytes() == raw for p, raw in before.items())
    _, policy = secured[7].load()
    user = replace(principal(), issuer=secured[0].config.issuer, org_id='org_mock', workspace_id='ws_mock',
                   subject='usr_owner', governance_roles=('workspace:owner',))
    restarted = WorkspaceProjects(directory)
    assert {p['id'] for p in restarted.read(user, policy, ProjectQuery())['items']} == {a, b}
    assert client.get('/api/data-catalog').status_code == 200
    assert client.get('/api/spaces').status_code == 200


def test_replay_revision_conflict_and_request_id_reuse_do_not_duplicate_audit(secured):
    _, client, _, _, _, _, scenes, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    saved = create(client, headers)
    assert create(client, headers)['replayed'] is True
    assert client.post('/api/data-projects', headers=headers, json={
        'action': 'create', 'name': 'Changed', 'request_id': 'a' * 32,
        'expected_revision': 0, 'reason': 'Synthetic fixture'}).json()['detail'] == 'project_request_id_reused'
    response = associate(client, headers, scenes[0]['id'], saved['project_id'], 0, 'b')
    assert response.status_code == 409 and response.json()['detail'] == 'project_revision_changed'
    response = associate(client, headers, scenes[0]['id'], saved['project_id'], 1, 'b')
    assert response.status_code == 200
    assert associate(client, headers, scenes[0]['id'], saved['project_id'], 1, 'b').json()['replayed'] is True
    assert client.get('/api/data-projects', params={'view': 'history'}).json()['total'] == 2


def test_reassignment_unlinking_and_archiving_preserve_history(secured):
    _, client, _, _, _, _, scenes, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    a = create(client, headers)['project_id']
    b = create(client, headers, 1, 'b', name='Other project')['project_id']
    assert associate(client, headers, scenes[0]['id'], a, 2, 'c').status_code == 200
    update = {'action': 'update', 'project_id': a, 'name': 'Archive survey', 'description': '',
              'status': 'archived', 'expected_revision': 3, 'request_id': 'd' * 32, 'reason': 'Archive'}
    response = client.post('/api/data-projects', headers=headers, json=update)
    assert response.status_code == 409 and response.json()['detail'] == 'project_has_scene_associations'
    assert associate(client, headers, scenes[0]['id'], b, 3, 'e').status_code == 200
    assert client.post('/api/data-projects', headers=headers, json=update | {'expected_revision': 4}).status_code == 200
    assert associate(client, headers, scenes[0]['id'], a, 5, 'f').json()['detail'] == 'active_project_required'
    assert associate(client, headers, scenes[0]['id'], None, 5, 'f').status_code == 200
    listing = client.get('/api/data-projects', params={'view': 'scenes'}).json()['items']
    assert listing[0]['project_id'] is None and listing[0]['association_state'] == 'unassigned'
    history = client.get('/api/data-projects', params={'view': 'history', 'project_id': a}).json()
    assert any(v['action'] == 'associate' and v['before']['project_id'] == a and v['after']['project_id'] == b
               for v in history['items'])


def test_legacy_project_adoption_is_explicit_and_does_not_guess_scene_membership(secured):
    _, client, _, _, _, directory, scenes, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    original = directory.read('project', scenes[0]['project_id'])
    saved = create(client, headers, action='adopt', legacy_project_id=original['id'], name='Confirmed legacy project')
    assert saved['project_id'] == original['id']
    assert saved['after']['legacy_project_id'] == original['id']
    assert directory.read('project', original['id']) == original
    assert client.get('/api/data-projects', params={'view': 'scenes'}).json()['items'][0]['project_id'] is None


def test_read_and_write_are_scope_bounded_and_do_not_reuse_scene_permissions(secured):
    rp, client, accounts, _, _, directory, scenes, policies, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    project = create(client, headers)['project_id']
    assert associate(client, headers, scenes[1]['id'], project, 1, 'b').status_code == 403
    assert associate(client, headers, scenes[0]['id'], project, 1, 'b').status_code == 200
    sign_in(secured, 'usr_engineer')
    assert [p['id'] for p in client.get('/api/data-projects').json()['items']] == [project]
    assert client.get('/api/data-projects', params={'view': 'history'}).status_code == 403
    sign_in(secured, 'usr_other')
    assert client.get('/api/data-projects').json()['items'] == []
    assert client.get('/api/data-projects', params={'project_id': project}).status_code == 403
    store = WorkspaceProjects(directory)
    user = replace(principal(), issuer=rp.config.issuer, org_id='org_mock', workspace_id='ws_mock',
                   subject='usr_manager', governance_roles=('workspace:owner',))
    _, policy = policies.load()
    for values in ({'issuer': 'https://foreign.test'}, {'org_id': 'org_other'}, {'workspace_id': 'ws_other'}):
        foreign = replace(user, **values)
        assert store.read(foreign, policy, ProjectQuery())['items'] == []
        command = ProjectChange.validate_python({'action': 'associate', 'space_id': scenes[0]['id'],
            'project_id': project, 'request_id': 'c'*32, 'expected_revision': 0, 'reason': 'Denied'})
        with pytest.raises(PermissionError):
            store.change(foreign, policy, command)


def test_privileged_project_directory_never_exposes_hidden_scene_counts_or_audit(secured):
    _, client, accounts, _, _, _, scenes, *_ = secured
    accounts.roles = ['workspace:owner']
    headers, _ = sign_in(secured, 'usr_owner')
    a = create(client, headers)['project_id']
    associate(client, headers, scenes[0]['id'], a, 1, 'b')
    associate(client, headers, scenes[1]['id'], a, 2, 'c')
    accounts.roles = ['workspace:member']
    sign_in(secured, 'usr_manager')
    project = client.get('/api/data-projects').json()['items'][0]
    assert project['scene_count'] == 1 and project['scene_count_scope'] == 'authorized_scenes'
    assert scenes[1]['id'] not in client.get('/api/data-projects', params={'view': 'history'}).text


def test_technical_directory_is_not_adopted_as_a_business_project(secured):
    rp, client, _, _, _, directory, scenes, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    scope = {'issuer': rp.config.issuer, 'org_id': 'org_mock', 'workspace_id': 'ws_mock'}
    for identity in ('project-' + checksum(scope)[:16],
                     'project-' + checksum({'workspace_scene_directory': scope})[:16]):
        response = client.post('/api/data-projects', headers=headers, json={
            'action': 'adopt', 'legacy_project_id': identity, 'name': 'Not a business project',
            'request_id': 'a'*32, 'expected_revision': 0, 'reason': 'Test technical directory'})
        assert response.status_code == 409
        assert response.json()['detail'] == 'technical_project_requires_explicit_association'
    assert client.get('/api/data-projects').json()['revision'] == 0


def test_authentication_csrf_validation_and_corrupt_store_fail_closed(secured):
    _, client, _, _, _, directory, *_ = secured
    assert client.get('/api/data-projects').status_code == 401
    headers, _ = sign_in(secured, 'usr_engineer')
    body = {'action': 'create', 'name': 'Denied', 'request_id': 'a'*32, 'expected_revision': 0, 'reason': 'Denied'}
    assert client.post('/api/data-projects', headers=headers, json=body).status_code == 403
    headers, _ = sign_in(secured, 'usr_manager')
    assert client.post('/api/data-projects', json=body).status_code == 403
    assert client.post('/api/data-projects', headers=headers | {'Origin': 'https://foreign.test'}, json=body).status_code == 403
    for invalid in ({'name': ' '}, {'reason': ' '}, {'workspace_id': 'foreign'}, {'actor': 'usr_owner'}, {'name': 'a'*101}):
        assert client.post('/api/data-projects', headers=headers, json=body | invalid).status_code == 422
    assert client.get('/api/data-projects', params={'workspace_id': 'foreign'}).status_code == 422
    assert client.get('/api/data-projects', params={'limit': 101}).status_code == 422
    assert client.put('/api/data-projects', headers=headers, json=body).status_code == 403
    path = directory.root / 'business-projects.sqlite3'
    path.write_bytes(b'not a database')
    assert client.get('/api/data-projects').status_code == 503
    assert client.post('/api/data-projects', headers=headers, json=body).status_code == 503
    assert path.read_bytes() == b'not a database'


def test_atomic_concurrent_changes_and_search_pagination(secured):
    rp, client, _, _, _, directory, _, policies, *_ = secured
    user = replace(principal(), issuer=rp.config.issuer, org_id='org_mock', workspace_id='ws_mock', subject='usr_manager')
    _, policy = policies.load()
    store = WorkspaceProjects(directory)
    command = ProjectChange.validate_python({'action': 'create', 'name': 'Park survey', 'request_id': 'a'*32,
                                             'expected_revision': 0, 'reason': 'Concurrent retry'})
    with ThreadPoolExecutor(max_workers=3) as pool:
        result = list(pool.map(lambda _: store.change(user, policy, command), range(3)))
    assert sum(not v['replayed'] for v in result) == 1
    headers, _ = sign_in(secured, 'usr_manager')
    create(client, headers, 1, 'b', name='Park inspection')
    page = client.get('/api/data-projects', params={'limit': 1}).json()
    assert page['total'] == 2 and page['next_offset'] == 1 and len(page['items']) == 1
    assert client.get('/api/data-projects', params={'q': 'inspection'}).json()['total'] == 1
    assert client.get('/api/data-projects', params={'offset': 1, 'limit': 1}).json()['next_offset'] is None


def test_distinct_concurrent_commands_require_refresh_instead_of_losing_changes(secured):
    rp, _, _, _, _, directory, _, policies, *_ = secured
    user = replace(principal(), issuer=rp.config.issuer, org_id='org_mock', workspace_id='ws_mock', subject='usr_manager')
    _, policy = policies.load()
    store = WorkspaceProjects(directory)

    def save(marker):
        command = ProjectChange.validate_python({'action': 'create', 'name': 'Concurrent ' + marker,
            'request_id': marker * 32, 'expected_revision': 0, 'reason': 'Distinct concurrent requests'})
        try:
            return store.change(user, policy, command)['revision']
        except ProjectError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['a', 'b']))
    assert set(results) == {1, 'project_revision_changed'}
    assert store.read(user, policy, ProjectQuery())['total'] == 1
