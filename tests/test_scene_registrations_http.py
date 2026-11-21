from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
import test_preview_publications

from test_platform_business import secured, sign_in
from test_platform_login import runtime
from packages.construction.preview_model import digest

PATH = '/api/scene-registrations'


@pytest.fixture(autouse=True)
def declared_three_dimensional_models(monkeypatch):
    original = test_preview_publications.make_preview
    def make(root):
        original(root)
        points = np.array([[0., 0., 2.], [4., 0., 2.], [0., 4., 2.], [4., 4., 2.],
                           [0., 0., 6.], [4., 0., 6.], [0., 4., 6.], [4., 4., 6.]])
        np.savez_compressed(root / 'spatial.npz', points=points,
                            colors=np.full((len(points), 3), 100, dtype='u1'))
        manifest = json.loads((root / 'model.json').read_bytes())
        manifest.update(axes=['right', 'forward', 'up'], unit='m')
        manifest['members']['spatial.npz']['sha256'] = digest(root / 'spatial.npz')
        (root / 'model.json').write_text(json.dumps(manifest), encoding='utf-8')
        return root
    monkeypatch.setattr(test_preview_publications, 'make_preview', make)


def prepared(secured):
    _, client, _, _, jobs, _, spaces, _, _, new = secured
    query = {'space_id': spaces[0]['id'], 'candidate_id': new['candidate_id']}
    response = client.get(PATH, params=query)
    assert response.status_code == 200, response.text
    state = response.json()
    doc = json.loads(Path('contracts/examples/spatial-registration-campus.json').read_text(encoding='utf-8'))
    doc.update(source=state['model_source'], synthetic=False,
               matrix=[[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]])
    bounds = np.asarray(doc['source']['bounds_m'])
    positions = np.asarray([[.1, .1, .1], [.9, .1, .2], [.1, .9, .3], [.9, .9, .4], [.3, .4, .8], [.7, .6, .9]])
    for control, point in zip(doc['controls'], bounds[0] + positions * (bounds[1] - bounds[0])):
        control.update(source_m=point.tolist(), target_m=point.tolist(), evidence_ref='HTTP fixture only')
    return query, state, doc


def command(query, state, action, revision, key, **extra):
    return {**query, 'source_sha256': state['source_sha256'], 'action': action,
            'expected_revision': revision, 'request_id': f'{key:032x}', 'reason': 'HTTP test evidence', **extra}


def test_scene_registration_auth_csrf_separate_review_and_fixed_adoption(secured, monkeypatch):
    _, client, _, _, jobs, directory, spaces, _, old, new = secured
    query = {'space_id': spaces[0]['id'], 'candidate_id': new['candidate_id']}
    assert client.get(PATH, params=query).status_code == 401
    viewer, _ = sign_in(secured)
    query, state, document = prepared(secured)
    assert not state['can_edit'] and not state['can_review']
    assert not (directory.root / 'scene-registrations.sqlite3').exists()
    assert client.get(PATH + '/geometry', params=query).status_code == 200
    save = command(query, state, 'save', 0, 1, document=document)
    assert client.post(PATH, headers=viewer, json=save).status_code == 403
    engineer, _ = sign_in(secured, 'usr_engineer')
    assert client.post(PATH, json=save).status_code == 403
    assert client.post(PATH, headers=engineer, json={**save, 'reviewed_by': 'forged'}).status_code == 422
    model_before = (jobs.model(new['candidate_id']).root / 'model.json').read_bytes()
    publication_before = client.get('/publications/' + old['id'] + '/api/preview').json()
    assert client.post(PATH, headers=engineer, json=save).status_code == 200
    assert client.post(PATH, headers=engineer, json=save).json()['revision'] == 1
    assert client.post(PATH, headers=engineer, json={**save, 'request_id': 'b' * 32}).status_code == 409
    submit = command(query, state, 'submit', 1, 2)
    assert client.post(PATH, headers=engineer, json=submit).status_code == 200
    approve = command(query, state, 'approve', 2, 3, approval={
        'evidence_note': 'HTTP fixture independent survey check', 'valid_from': '2020-01-01T00:00:00Z',
        'valid_until': '2099-01-01T00:00:00Z', 'bounds_m': document['source']['bounds_m'],
        'control_evidence_verified': True, 'independent_checks_verified': True,
        'datum_verified': True, 'extent_verified': True})
    assert client.post(PATH, headers=engineer, json=approve).status_code == 403
    manager, _ = sign_in(secured, 'usr_manager')
    result = client.post(PATH, headers=manager, json=approve)
    assert result.status_code == 200, result.text
    assert result.json()['adopted_revision'] is None
    assert client.post(PATH, headers=manager, json=command(query, state, 'adopt', 3, 4)).status_code == 200
    adopted = client.get(PATH, params=query).json()
    assert adopted['adopted']['reviewed_by'] == 'usr_manager'
    assert adopted['adopted']['authored_by'] == 'usr_engineer'
    assert not adopted['can_focus_geographic_map']
    assert client.get(PATH, params={**query, 'revision': '1'}).json()['review_status'] == 'draft'
    assert client.get(PATH, params={**query, 'workspace_scope': 'forged'}).status_code == 422
    assert (jobs.model(new['candidate_id']).root / 'model.json').read_bytes() == model_before
    assert client.get('/publications/' + old['id'] + '/api/preview').json() == publication_before
    def inactive(*args):
        raise ValueError('lifecycle_archived_new_use_blocked')
    monkeypatch.setattr(type(jobs.controls), 'require_active', inactive)
    assert client.get(PATH, params=query).status_code == 200
    assert client.post(PATH, headers=manager, json=command(query, state, 'clear_adoption', 4, 5)).status_code == 409


def test_denied_registration_has_no_model_io_or_store_creation(secured, monkeypatch):
    _, client, _, _, jobs, directory, spaces, _, _, new = secured
    sign_in(secured, 'usr_other')
    def forbidden(*args, **kwargs):
        raise AssertionError('authorization must precede model access')
    monkeypatch.setattr(jobs, 'model', forbidden)
    for suffix in ('', '/geometry', '/source'):
        assert client.get(PATH + suffix, params={'space_id': spaces[0]['id'],
                                                'candidate_id': new['candidate_id']}).status_code == 403
    assert not (directory.root / 'scene-registrations.sqlite3').exists()


def test_blocked_source_diagnostic_is_authorized_bound_and_read_only(secured):
    _,client,_,_,jobs,directory,spaces,_,_,new=secured
    query={'space_id':spaces[0]['id'],'candidate_id':new['candidate_id']}
    assert client.get(PATH+'/source',params=query).status_code==401
    sign_in(secured,'usr_engineer')
    model=jobs.model(new['candidate_id']);manifest=dict(model.manifest,axes=['x','y','z'])
    (model.root/'model.json').write_text(json.dumps(manifest),encoding='utf-8')
    before=(model.root/'model.json').read_bytes()
    assert client.get(PATH,params=query).status_code==409
    response=client.get(PATH+'/source',params=query)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['profile']=='cospace.registration-source/0.1' and result['candidate_id']==new['candidate_id']
    assert result['registration_readiness']['status']=='needs_declaration' and result['can_manage_input']
    assert result['input_id']==manifest['source']['input_binding']['id']
    sign_in(secured)
    assert not client.get(PATH+'/source',params=query).json()['can_manage_input']
    assert client.post(PATH+'/source',json=query).status_code==403
    assert client.get(PATH+'/source',params=query|{'revision':'1'}).status_code==422
    assert client.get(PATH+'/source',params=query|{'space_id':spaces[1]['id']}).status_code==403
    assert (model.root/'model.json').read_bytes()==before
    assert not (directory.root/'scene-registrations.sqlite3').exists()


@pytest.mark.parametrize('axes',[['右','前','上'],['R','F','U'],['N','E','D'],['Right','Down','Forward']])
def test_explicit_axis_alias_models_open_without_rewriting_them(secured,axes):
    _,client,_,_,jobs,_,spaces,_,_,new=secured
    sign_in(secured)
    model=jobs.model(new['candidate_id']);manifest=dict(model.manifest,axes=axes)
    (model.root/'model.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    before=(model.root/'model.json').read_bytes()
    response=client.get(PATH,params={'space_id':spaces[0]['id'],'candidate_id':new['candidate_id']})
    assert response.status_code==200,response.text
    assert response.json()['model_source']['axes']==axes
    assert (model.root/'model.json').read_bytes()==before


def test_registration_source_binding_and_workspace_boundary(secured):
    _, client, accounts, _, _, _, spaces, _, _, _ = secured
    headers, _ = sign_in(secured, 'usr_engineer')
    query, state, document = prepared(secured)
    wrong = deepcopy(document)
    wrong['source']['bounds_m'][1][0] += 1
    response = client.post(PATH, headers=headers, json=command(query, state, 'save', 0, 1, document=wrong))
    assert response.status_code == 409, response.text
    for change in ({'space_id': spaces[1]['id']}, {'candidate_id': '../outside'}):
        assert client.get(PATH, params=query | change).status_code == 403
    assert client.post(PATH, headers=headers, json=command(query, state, 'save', 0, 2, document=document)).status_code == 200
    accounts.workspace = 'ws_other'
    sign_in(secured, 'usr_engineer')
    assert client.get(PATH, params=query).status_code == 403


def test_check_is_authorized_nonpersistent_and_recomputes_the_document(secured):
    _, client, _, _, _, directory, *_ = secured
    sign_in(secured)
    query, state, document = prepared(secured)
    body = {**query, 'source_sha256': state['source_sha256'], 'document': document}
    assert client.post(PATH + '/check', json=body).status_code == 403
    headers, _ = sign_in(secured, 'usr_engineer')
    checked = client.post(PATH + '/check', json=body, headers=headers)
    assert checked.status_code == 200, checked.text
    assert checked.json()['document'] == document
    assert checked.json()['report']['calculation_status'] == 'checks_passed'
    assert client.post(PATH + '/check', json={**body, 'report': {'passed': True}}, headers=headers).status_code == 422
    invalid = deepcopy(body)
    invalid['document']['matrix'][0][0] = 2.
    assert client.post(PATH + '/check', json=invalid, headers=headers).status_code == 422
    assert not (directory.root / 'scene-registrations.sqlite3').exists()


@pytest.mark.parametrize('field,value,code', [
    ('axes', [], 'registration_source_axes_unsupported'),
    ('unit', 'mm', 'registration_source_unit_unsupported'),
])
def test_undeclared_source_frame_is_rejected(secured, field, value, code):
    _, client, _, _, jobs, directory, spaces, _, _, new = secured
    sign_in(secured)
    model = jobs.model(new['candidate_id'])
    manifest = dict(model.manifest, **{field: value})
    (model.root / 'model.json').write_text(json.dumps(manifest), encoding='utf-8')
    response = client.get(PATH, params={'space_id': spaces[0]['id'], 'candidate_id': new['candidate_id']})
    assert response.status_code == 409, response.text
    assert code in response.text
    assert not (directory.root / 'scene-registrations.sqlite3').exists()
