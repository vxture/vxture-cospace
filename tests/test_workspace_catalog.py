import json
import pytest
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from packages.service.space_access import SpaceAccessPolicy


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_catalog_requires_session_and_does_not_expand_preview_grants(secured):
    _, client, _, _, _, _, spaces, *_ = secured
    assert client.get('/api/data-catalog').status_code == 401
    sign_in(secured)
    response = client.get('/api/data-catalog')
    assert response.status_code == 200
    assert response.json()['items'] == response.json()['spaces'] == []
    assert client.get('/api/data-catalog', params={'space_id': spaces[0]['id']}).status_code == 403
    assert client.post('/api/data-catalog', json={}).status_code == 403


def test_authorized_catalog_is_read_only_and_contains_process_and_results(secured, monkeypatch):
    _, client, _, _, jobs, _, spaces, *_ = secured
    sign_in(secured, 'usr_engineer')
    def forbidden(*args, **kwargs):
        pytest.fail('metadata reads must never poll, resolve source or start work')
    monkeypatch.setattr(jobs, 'poll', forbidden)
    monkeypatch.setattr(jobs.inputs, 'resolve', forbidden)
    monkeypatch.setattr(jobs, 'start', forbidden)
    before = files(jobs.root.parent)
    response = client.get('/api/data-catalog')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'ready', body
    assert {i['kind'] for i in body['items']} >= {'input', 'job', 'candidate', 'publication', 'human_view', 'agent_view'}
    exports = [i for i in body['items'] if i['kind'] == 'offline_package']
    assert exports and all(i['state'] == 'export_on_request' and i['href'].startswith('#delivery?') for i in exports)
    assert all(i['space_id'] == spaces[0]['id'] and i['integrity'] == 'metadata_only' for i in body['items'])
    assert spaces[1]['id'] not in response.text
    assert str(jobs.root) not in response.text and 'snapshot' not in response.text
    assert not body['source_files_rechecked'] and not body['consumer_state_checked']
    assert files(jobs.root.parent) == before
    assert response.headers['cache-control'] == 'no-store'


def test_failed_task_is_process_record_not_candidate(secured):
    _, client, _, _, jobs, _, spaces, *_ = secured
    sign_in(secured, 'usr_engineer')
    root = jobs.root / 'build-failed';root.mkdir()
    (root / 'job.json').write_text(json.dumps({'id': root.name, 'space_id': spaces[0]['id'],
        'project_id': spaces[0]['project_id'], 'state': 'failed', 'error': 'private filesystem detail'}))
    items = client.get('/api/data-catalog').json()['items']
    assert len([i for i in items if i['record_id'] == root.name]) == 1
    assert next(i for i in items if i['record_id'] == root.name)['kind'] == 'job'
    assert 'private filesystem detail' not in json.dumps(items)


def test_view_recovery_is_not_unknown_or_a_finished_candidate(secured):
    _, client, _, _, jobs, _, spaces, *_ = secured
    sign_in(secured,'usr_engineer')
    root=jobs.root/'build-view-recovery';root.mkdir()
    (root/'job.json').write_text(json.dumps({'id':root.name,'space_id':spaces[0]['id'],
        'project_id':spaces[0]['project_id'],'state':'views_failed'}))
    rows=[i for i in client.get('/api/data-catalog').json()['items'] if i['record_id']==root.name]
    assert len(rows)==1 and rows[0]['kind']=='job' and rows[0]['state']=='views_failed'


def test_filters_pagination_validation_and_partial_failure(secured):
    _, client, _, _, jobs, _, spaces, *_ = secured
    sign_in(secured, 'usr_engineer')
    all_items = client.get('/api/data-catalog').json()['items']
    pages = []
    for offset in range(0, len(all_items), 2):
        value = client.get('/api/data-catalog', params={'limit': 2, 'offset': offset}).json()
        pages.extend(value['items'])
    assert pages == all_items
    original = client.get('/api/data-catalog', params={'category': 'original'}).json()
    assert original['items'] and all(i['category'] == 'original' for i in original['items'])
    assert client.get('/api/data-catalog', params={'search': 'no-such-record'}).json()['total'] == 0
    for query in ({'limit': 101}, {'offset': -1}, {'category': 'bad'}, {'workspace_id': 'foreign'}, {'limit': '1.1'}):
        assert client.get('/api/data-catalog', params=query).status_code == 422
    assert client.get('/api/data-catalog?limit=1&limit=2').status_code == 403
    (jobs.root / 'build-corrupt').mkdir()
    (jobs.root / 'build-corrupt' / 'job.json').write_text('invalid')
    partial = client.get('/api/data-catalog').json()
    assert partial['status'] == 'partial' and partial['items']
    assert 'build-corrupt' not in json.dumps(partial)


def test_workspace_and_revocation_are_checked_each_request(secured):
    _, client, accounts, _, _, _, spaces, policies, *_ = secured
    sign_in(secured, 'usr_engineer')
    assert client.get('/api/data-catalog').json()['items']
    revision, policy = policies.load()
    policies.replace(SpaceAccessPolicy(bindings=policy.bindings, grants=[]), expected_revision=revision,
                     actor='test', reason='revoke')
    assert client.get('/api/data-catalog').json()['items'] == []
    assert client.get('/api/data-catalog', params={'space_id': spaces[0]['id']}).status_code == 403
    accounts.workspace = 'foreign-workspace'
    sign_in(secured, 'usr_engineer')
    assert client.get('/api/data-catalog').json()['spaces'] == []


def test_owner_can_filter_all_bound_scenes_but_not_foreign_workspace(secured):
    _, client, accounts, _, _, _, spaces, *_ = secured
    accounts.roles = ['workspace:owner'];sign_in(secured, 'usr_owner')
    body = client.get('/api/data-catalog').json()
    assert {s['id'] for s in body['spaces']} == {s['id'] for s in spaces}
    selected = client.get('/api/data-catalog', params={'space_id': spaces[1]['id']}).json()
    assert all(i['space_id'] == spaces[1]['id'] for i in selected['items'])
    accounts.workspace = 'foreign-workspace';sign_in(secured, 'usr_owner')
    assert client.get('/api/data-catalog').json()['spaces'] == []


def test_catalog_metadata_budget_fails_explicitly(secured, monkeypatch):
    _, client, *_ = secured;sign_in(secured, 'usr_engineer')
    monkeypatch.setattr('packages.data.workspace_catalog.MAX_RECORDS', 1)
    result = client.get('/api/data-catalog')
    assert result.status_code == 503 and result.json()['detail'] == 'catalog_budget_exceeded'


def test_batch_attachment_and_saved_preflight_keep_original_identity(secured):
    from packages.data.preview_batches import PreviewBatches, BatchDraft
    from packages.data.scene_attachments import SceneAttachments
    from packages.data.preflight_records import PreflightRecords
    _, client, _, _, jobs, _, spaces, *_ = secured
    sign_in(secured, 'usr_engineer')
    space = spaces[0]['id']
    identity = json.loads((jobs.root / 'build-one' / 'job.json').read_bytes())['input_id']
    batches = PreviewBatches(jobs.inputs)
    saved = batches.create(BatchDraft(space_id=space, name='N2 批次', origin='imported_sample', note='test'))
    # PreviewJobs exposes batches as a derived property backed by these inputs.
    source = jobs.inputs.root / 'fixture-reference.txt';source.write_text('reference')
    attachment = SceneAttachments(jobs.inputs).register(source, space, 'reference.txt', 'usr_test')['attachment']
    checks = PreflightRecords(jobs.inputs)
    check = checks.save(identity, {'input_id': identity, 'status': 'passed', 'checked_at': '2026-11-07T00:00:00Z'},
                        'usr_test', checks.fingerprint(identity))
    before = files(jobs.root.parent)
    report = client.get('/api/data-catalog').json()
    assert report['status'] == 'ready', report
    values = {i['kind']: i for i in report['items'] if i['kind'] in ('batch', 'attachment', 'preflight')}
    assert values['batch']['record_id'] == saved['id']
    assert values['attachment']['record_id'] == attachment['id']
    assert values['preflight']['record_id'] == identity + '@' + str(check['sequence'])
    assert files(jobs.root.parent) == before


def test_unknown_foreign_records_and_broken_views_do_not_claim_integrity(secured):
    _, client, _, _, jobs, _, spaces, *_ = secured
    sign_in(secured, 'usr_engineer')
    path = jobs.root / 'build-foreign';path.mkdir()
    (path / 'job.json').write_text(json.dumps({'id':path.name,'space_id':spaces[1]['id'],'state':'failed','error':'secret'}))
    response = client.get('/api/data-catalog')
    assert 'build-foreign' not in response.text and 'secret' not in response.text
    (jobs.root / 'build-one' / 'output' / 'model.json').write_text('{}')
    body = client.get('/api/data-catalog').json()
    assert body['status'] == 'partial'
    assert any(i['kind'] == 'candidate' and i['record_id'] == 'build-one' for i in body['items'])
    assert not any(i['kind'] in ('human_view', 'agent_view') and i['record_id'] == 'build-one' for i in body['items'])


def test_path_escape_is_reported_without_reading_external_payload(secured):
    _, client, _, _, jobs, _, spaces, *_ = secured
    sign_in(secured, 'usr_engineer')
    outside = jobs.root.parent / 'private-job.json'
    outside.write_text(json.dumps({'id':'build-escape','space_id':spaces[0]['id'],
        'project_id':spaces[0]['project_id'],'state':'failed','private':'sensitive-content'}))
    folder = jobs.root / 'build-escape';folder.mkdir()
    try:
        (folder / 'job.json').symlink_to(outside)
    except OSError:
        pytest.skip('symlink creation unavailable on this host')
    body = client.get('/api/data-catalog')
    assert body.status_code == 200 and body.json()['status'] == 'partial'
    assert 'build-escape' not in body.text and 'sensitive-content' not in body.text
