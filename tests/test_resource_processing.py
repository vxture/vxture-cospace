"""Saved processing bindings only; geometry is never needed to inspect the chain."""
import json
from pathlib import Path

import pytest

from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_workspace_projects import create
from test_workspace_resources import register
from test_resource_files import upload
from test_preview_workflow import inventory


def registered_input(s):
    client = s[1]
    headers, _ = sign_in(s, 'usr_manager')
    project = create(client, headers)['project_id']
    item = next(i for i in client.get('/api/data-resources').json()['items'] if i['kind'] == 'input')
    assert register(client, headers, item, project).status_code == 200
    return item, headers


def processing(client, identity, **values):
    return client.get('/api/data-processing', params={'resource_id': identity} | values)


def test_metadata_graph_has_real_input_jobs_candidates_views_and_fixed_publications_without_io(secured, monkeypatch):
    _, client, _, _, jobs, directory, scenes, *_ = secured
    item, _ = registered_input(secured)
    monkeypatch.setattr(jobs, 'poll', lambda *a: pytest.fail('must not poll'))
    monkeypatch.setattr(jobs, 'model', lambda *a: pytest.fail('must not load models'))
    monkeypatch.setattr(jobs.inputs, 'resolve', lambda *a: pytest.fail('must not resolve input bytes'))
    original = Path.open
    def metadata_only(path, *args, **kwargs):
        if path.is_relative_to(jobs.root) or path.is_relative_to(jobs.inputs.root):
            assert path.suffix in ('.json', '.sqlite3'), path
        return original(path, *args, **kwargs)
    before = inventory(directory.root.parent)
    with monkeypatch.context() as m:
        m.setattr(Path, 'open', metadata_only)
        response = processing(client, item['resource_id'])
    assert response.status_code == 200, response.text
    r = response.json()
    assert r['status'] == 'ready'
    assert {n['kind'] for n in r['nodes']} == {'input', 'job', 'candidate', 'human_view', 'agent_view', 'publication'}
    assert sum(n['kind'] == 'candidate' for n in r['nodes']) == 4
    assert sum(n['kind'] == 'publication' for n in r['nodes']) == 2
    assert {e['status'] for e in r['edges']} == {'matched'}
    assert 'derived_from' in {e['relation'] for e in r['edges']}
    assert not r['source_files_rechecked']
    assert not r['jobs_polled']
    assert str(jobs.root) not in response.text
    assert scenes[1]['id'] not in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert inventory(directory.root.parent) == before
    assert client.head('/api/data-processing', params={'resource_id': item['resource_id']}).status_code == 200


@pytest.mark.parametrize('mode', ['failed', 'queued', 'running', 'mismatched_binding', 'foreign_input', 'missing_model', 'publication_snapshot', 'missing_input'])
def test_unfinished_or_broken_bindings_never_look_like_verified_output(secured, mode):
    _, client, _, _, jobs, _, scenes, *_ = secured
    item, _ = registered_input(secured)
    jobpath = jobs.root/'build-one/job.json'; job = json.loads(jobpath.read_bytes())
    if mode in ('failed', 'queued', 'running'):
        job['state'] = mode
    elif mode == 'mismatched_binding':
        job['input_binding']['snapshot_sha256'] = '0'*64
    elif mode == 'foreign_input':
        job['input_id'] = 'input-'+'f'*16
        job['input_binding']['space_id'] = scenes[1]['id']
    elif mode == 'missing_model':
        (jobs.root/'build-one/output/model.json').unlink()
    elif mode == 'publication_snapshot':
        path = next((jobs.root/'publications').glob('*/model.json'))
        changed_publication = path.parent.name
        path.write_text('{}')
    else:
        (jobs.inputs.root/(item['record_id']+'.json')).unlink()
    jobpath.write_text(json.dumps(job))
    response = processing(client, item['resource_id'])
    assert response.status_code == 200, response.text
    r = response.json()
    if mode in ('failed', 'queued', 'running'):
        assert not any(n['key'] == 'candidate:build-one' for n in r['nodes'])
        assert any(n['key'] == 'job:build-one' and n['state'] == mode for n in r['nodes'])
    else:
        assert r['status'] == 'partial'
    if mode == 'publication_snapshot':
        assert next(e for e in r['edges'] if e['from'] == 'publication:'+changed_publication)['status'] == 'unresolved'
    assert scenes[1]['id'] not in response.text
    assert 'input-'+'f'*16 not in response.text


def test_reference_file_does_not_invent_processing_and_access_is_source_only(secured):
    _, client, accounts, *_ = secured
    headers, _ = sign_in(secured, 'usr_manager')
    identity = upload(client, headers).json()['resource_id']
    assert processing(client, identity).json()['status'] == 'not_applicable'
    assert processing(client, identity, project_id='project-'+'a'*16).status_code == 422
    sign_in(secured, 'usr_engineer')
    assert processing(client, identity).status_code == 403
    accounts.workspace = 'other'; accounts.roles = ['workspace:owner']; sign_in(secured, 'usr_owner')
    assert processing(client, identity).status_code == 403


@pytest.mark.parametrize('damage', ['job_json', 'model_source', 'view_member', 'budget', 'no_input_store'])
def test_corrupt_or_excessive_metadata_is_not_a_complete_graph(secured, monkeypatch, damage):
    _, client, _, _, jobs, *_ = secured
    item, _ = registered_input(secured)
    path = jobs.root/'build-one/output/model.json'
    if damage == 'job_json':
        (jobs.root/'build-one/job.json').write_text('broken')
    elif damage == 'budget':
        monkeypatch.setattr('packages.data.resource_processing.MAX_RECORDS', 1)
    elif damage == 'no_input_store':
        jobs.inputs = None
    else:
        value = json.loads(path.read_bytes())
        if damage == 'model_source':
            value['source'] = []
        else:
            value['members'] = {}
        path.write_text(json.dumps(value))
    response = processing(client, item['resource_id'])
    if damage == 'budget':
        assert response.status_code == 503
    else:
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'partial'
