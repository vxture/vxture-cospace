"""D01-D04 release journey: project reuse never mutates fixed scene deliveries."""
import json
import sqlite3
from uuid import uuid4

from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_preview_workflow import inventory
from test_resource_files import upload, file_item, download
from test_resource_governance import command, report
from test_resource_sharing import shared, change, grant, use
from test_resource_versions import append, upgrade, compare
from test_workspace_resources import register


def test_project_original_to_explicit_upgrade_and_recoverable_archive(shared, tmp_path):
    s = shared
    client, identity_context = s['client'], s['secured']
    frozen_jobs = inventory(s['jobs'].root)
    frozen_inputs = inventory(s['jobs'].inputs.root)
    source = next(i for i in client.get('/api/data-resources').json()['items'] if i['kind'] == 'input')
    assert register(client, s['headers'], source, s['a'], request_id=uuid4().hex).status_code == 200
    graph = client.get('/api/data-processing', params={'resource_id': source['resource_id']})
    assert graph.status_code == 200, graph.text
    assert graph.json()['status'] == 'ready'
    assert {n['kind'] for n in graph.json()['nodes']} >= {'input', 'job', 'candidate', 'publication'}

    uploaded = upload(client, s['headers'], s['a'], payload=b'E,N,U\n100,200,30\n')
    assert uploaded.status_code == 201, uploaded.text
    identity = uploaded.json()['resource_id']
    s['item'] = old = file_item(client, identity)
    assert old['is_base']
    assert old['owner_project_id'] == s['a']
    assert client.get('/api/data-processing', params={'resource_id': identity}).json()['status'] == 'not_applicable'
    s['old_grant'] = grant(s)

    c_headers, _ = sign_in(identity_context, 'usr_c')
    assert use(s, c_headers, s['old_grant']).status_code == 403
    assert download(client, old).status_code == 403
    assert not any(i['resource_id'] == identity for i in client.get('/api/data-resources').json()['items'])

    b_headers, _ = sign_in(identity_context, 'usr_other')
    result = use(s, b_headers, s['old_grant'], space_id=s['scenes'][1]['id'])
    assert result.status_code == 200, result.text
    s['use'] = result.json()['after']
    assert s['use']['coordinate_status'] == 'not_applied'
    assert client.get('/api/spaces/'+s['scenes'][0]['id']).status_code == 403

    s['headers'], _ = sign_in(identity_context, 'usr_manager')
    assert file_item(client, identity)['is_shared']
    assert append(client, s['headers'], old, payload=b'E,N,U\n101,201,31\n').status_code == 201
    current = file_item(client, identity)
    response = change(client, s['headers'], 'grant', resource_id=identity,
                      version_id=current['source_version']['version_id'], expected_resource_revision=2,
                      target_project_id=s['b'], allow_download=True)
    assert response.status_code == 200, response.text
    s['new_grant'] = response.json()['after']
    # A source manager receives dependency facts, never hidden receiving-project details.
    impact = report(client, identity)
    assert impact.json()['impact'] == {'scope': 'workspace', 'has_linked_references': True, 'has_active_grants': True}
    assert s['scenes'][1]['id'] not in impact.text
    assert command(client, s['headers'], identity)[1].status_code == 409

    b_headers, _ = sign_in(identity_context, 'usr_other')
    reference = next(i for i in client.get('/api/data-resources', params={'project_id': s['b']}).json()['items']
                     if i['resource_id'] == identity)
    assert reference['external']
    assert not reference['can_manage']
    assert reference['href'] is None
    assert reference['uses'][0]['version_id'] == old['source_version']['version_id']
    assert compare(s).json()['total'] == 1
    response = upgrade(s, b_headers)
    assert response.status_code == 200, response.text
    upgraded = response.json()['after']
    for key in ('id', 'project_id', 'space_id', 'purpose', 'coordinate_status', 'resource_id'):
        assert upgraded[key] == s['use'][key]
    assert upgraded['version_id'] == current['source_version']['version_id']
    assert upgraded['revision'] == 2
    for granted, expected in ((s['old_grant'], b'E,N,U\n100,200,30\n'), (s['new_grant'], b'E,N,U\n101,201,31\n')):
        assert client.get('/api/data-sharing/download', params={'grant_id': granted['id'],
                          'grant_revision': granted['revision'], 'project_id': s['b']}).content == expected

    s['headers'], _ = sign_in(identity_context, 'usr_manager')
    for granted in (s['old_grant'], s['new_grant']):
        assert change(client, s['headers'], 'revoke', grant_id=granted['id'], expected_revision=1).status_code == 200
    blocked = command(client, s['headers'], identity)[1]
    assert blocked.status_code == 409
    assert blocked.json()['detail'] == 'resource_has_references'
    b_headers, _ = sign_in(identity_context, 'usr_other')
    assert change(client, b_headers, 'unlink', use_id=upgraded['id'], expected_revision=2).status_code == 200
    s['headers'], _ = sign_in(identity_context, 'usr_manager')
    assert command(client, s['headers'], identity)[1].status_code == 200
    archived = client.get('/api/data-resources', params={'project_id': s['a'], 'lifecycle': 'archived'}).json()
    assert [i['resource_id'] for i in archived['items']] == [identity]
    assert append(client, s['headers'], current).json()['detail'] == 'resource_archived'
    assert download(client, old).content == b'E,N,U\n100,200,30\n'
    assert download(client, current).content == b'E,N,U\n101,201,31\n'

    # A real SQLite backup preserves archived state, both versions and upgrade audit.
    checkpoint = tmp_path/'business-projects.sqlite3'
    with sqlite3.connect(s['directory'].root/checkpoint.name) as db, sqlite3.connect(checkpoint) as copied:
        db.backup(copied)
    with sqlite3.connect(checkpoint) as copied:
        state = copied.execute('SELECT record FROM data_resource_states WHERE id=?', (identity,)).fetchone()
        assert json.loads(state[0])['state'] == 'archived'
        assert copied.execute('SELECT COUNT(*) FROM data_resource_file_history').fetchone()[0] == 1
        assert copied.execute('SELECT COUNT(*) FROM data_governance_changes').fetchone()[0] == 1
        changes = [json.loads(row[0]) for row in copied.execute('SELECT record FROM data_sharing_changes')]
        assert any(row['action'] == 'upgrade' for row in changes)

    assert command(client, s['headers'], identity, 'restore')[1].status_code == 200
    assert file_item(client, identity)['lifecycle_state'] == 'active'
    sign_in(identity_context, 'usr_other')
    assert client.get('/api/data-sharing', params={'view': 'uses', 'project_id': s['b']}).json()['items'][0]['status'] == 'unlinked'
    assert not any(i['resource_id'] == identity for i in client.get('/api/data-resources', params={'project_id': s['b']}).json()['items'])
    assert inventory(s['jobs'].root) == frozen_jobs
    assert inventory(s['jobs'].inputs.root) == frozen_inputs
