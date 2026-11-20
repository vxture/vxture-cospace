import json

from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_scene_ontology_links import publish_core
from test_preview_control import run as control_change
from packages.service.preview_publications import PreviewPublications


PATH = '/api/scene-ontology-links'


def test_scene_links_authorization_published_definition_and_fixed_source(secured):
    rp, client, accounts, _, jobs, directory, spaces, _, old, new = secured
    query = {'space_id': spaces[0]['id'], 'candidate_id': new['candidate_id']}
    assert client.get(PATH, params=query).status_code == 401
    headers, _ = sign_in(secured, 'usr_local_test')
    initial = client.get(PATH, params=query)
    assert initial.status_code == 200, initial.text
    assert not initial.json()['can_edit'] and not initial.json()['options']
    assert initial.json()['objects']
    scope = json.dumps([rp.config.issuer, 'org_mock', 'ws_mock'], separators=(',', ':'))
    reference = publish_core(directory.root, scope)
    body = {**query, 'source_sha256': initial.json()['source_sha256'], 'object_id': initial.json()['objects'][0]['object_id'],
            'action': 'set', 'reference': reference, 'concept_id': 'physical_object',
            'expected_revision': 0, 'request_id': 'a' * 32}
    assert client.post(PATH, json=body, headers=headers).status_code == 403
    headers, _ = sign_in(secured, 'usr_engineer')
    publication_before = client.get('/publications/' + old['id'] + '/api/objects').json()
    assert client.post(PATH, json=body).status_code == 403
    assert client.post(PATH, json={**body, 'actor': 'forged'}, headers=headers).status_code == 422
    manifest_before = (jobs.model(new['candidate_id']).root / 'model.json').read_bytes()
    result = client.post(PATH, json=body, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()['revision'] == 1
    assert client.post(PATH, json=body, headers=headers).json()['revision'] == 1
    assert client.post(PATH, json={**body, 'request_id': 'b' * 32}, headers=headers).status_code == 409
    saved = client.get(PATH, params=query).json()
    assert saved['links'][0]['reference'] == reference
    assert saved['links'][0]['linked_by'] == 'usr_engineer'
    assert saved['instance_validation'] == 'attributes_checked' and not saved['included_in_publication']
    assert (jobs.model(new['candidate_id']).root / 'model.json').read_bytes() == manifest_before
    assert client.get('/publications/' + old['id'] + '/api/objects').json() == publication_before
    assert client.get(PATH, params={**query, 'workspace_id': 'forged'}).status_code == 422
    assert client.get(PATH, params={**query, 'space_id': spaces[1]['id']}).status_code == 403
    assert client.get(PATH, params={**query, 'candidate_id': 'build-one'}).json()['links'] == []
    sign_in(secured, 'usr_other')
    assert client.get(PATH, params=query).status_code == 403
    accounts.workspace = 'ws_other'
    sign_in(secured, 'usr_engineer')
    assert client.get(PATH, params=query).status_code == 403


def test_denied_request_does_not_open_model_or_create_link_store(secured, monkeypatch):
    _, client, _, _, jobs, directory, spaces, _, _, new = secured
    sign_in(secured, 'usr_other')
    def forbidden(*args, **kwargs):
        raise AssertionError('authorization must precede model reads')
    monkeypatch.setattr(jobs, 'model', forbidden)
    assert client.get(PATH, params={'space_id': spaces[0]['id'], 'candidate_id': new['candidate_id']}).status_code == 403
    assert not (directory.root / 'scene-ontology-links.sqlite3').exists()


def test_archived_candidate_remains_readable_but_cannot_gain_links(secured):
    rp, client, _, _, jobs, directory, spaces, _, old, _ = secured
    query = {'space_id': spaces[0]['id'], 'candidate_id': old['candidate_id']}
    headers, _ = sign_in(secured, 'usr_engineer')
    before = client.get(PATH, params=query).json()
    scope = json.dumps([rp.config.issuer, 'org_mock', 'ws_mock'], separators=(',', ':'))
    reference = publish_core(directory.root, scope)
    control_change(jobs.controls, PreviewPublications(jobs), spaces[0]['id'],
                   'candidate:' + old['candidate_id'], 'archive_candidate')
    assert client.get(PATH, params=query).status_code == 200
    response = client.post(PATH, headers=headers, json={**query, 'action': 'set',
        'object_id': before['objects'][0]['object_id'], 'reference': reference, 'concept_id': 'physical_object',
        'source_sha256': before['source_sha256'], 'request_id': 'a' * 32, 'expected_revision': 0})
    assert response.status_code == 409, response.text
    assert response.json()['detail'] == 'link_source_inactive'
    assert client.get(PATH, params=query).json()['revision'] == 0


def test_properties_authorization_validation_and_source_isolation(secured):
    rp, client, _, _, jobs, directory, spaces, _, old, new = secured
    query = {'space_id':spaces[0]['id'], 'candidate_id':old['candidate_id']}
    headers, _ = sign_in(secured, 'usr_engineer')
    initial = client.get(PATH, params=query).json()
    scope = json.dumps([rp.config.issuer, 'org_mock', 'ws_mock'], separators=(',', ':'))
    reference = publish_core(directory.root, scope)
    base = {**query, 'source_sha256':initial['source_sha256'], 'object_id':initial['objects'][0]['object_id']}
    manifest = (jobs.model(old['candidate_id']).root/'model.json').read_bytes()
    publication = client.get('/publications/'+old['id']+'/api/objects').json()
    assert client.post(PATH, headers=headers, json={**base, 'action':'set', 'reference':reference,
        'concept_id':'physical_object', 'request_id':'a'*32, 'expected_revision':0}).status_code==200
    body = {**base, 'action':'properties', 'properties':{'name':{'value':'manual declaration'}},
            'valid_time':None, 'evidence_note':'manual inspection pending', 'request_id':'b'*32, 'expected_revision':1}
    assert client.post(PATH, json=body).status_code==403
    for field in ('properties', 'valid_time', 'evidence_note'):
        malformed = dict(body)
        del malformed[field]
        response = client.post(PATH, headers=headers, json=malformed)
        assert response.status_code==422, response.text
    response = client.post(PATH, headers=headers, json=body)
    assert response.status_code==200, response.text
    assert response.json()['revision']==2
    assert client.post(PATH, headers=headers, json=body).json()['revision']==2
    saved = client.get(PATH, params=query).json()
    assert saved['instance_report']['valid'] and not saved['included_in_publication']
    assert saved['links'][0]['properties_updated_by']=='usr_engineer'
    bad = {**body, 'properties':{'name':{'value':False}}, 'request_id':'c'*32, 'expected_revision':2}
    assert client.post(PATH, headers=headers, json=bad).status_code==200
    assert not client.get(PATH, params=query).json()['instance_report']['valid']
    readonly, _ = sign_in(secured, 'usr_local_test')
    assert client.post(PATH, headers=readonly, json=bad).status_code==403
    headers, _ = sign_in(secured, 'usr_engineer')
    control_change(jobs.controls, PreviewPublications(jobs), spaces[0]['id'],
                   'candidate:'+old['candidate_id'], 'archive_candidate')
    assert client.post(PATH, headers=headers, json={**bad, 'request_id':'d'*32, 'expected_revision':3}).status_code==409
    assert client.get(PATH, params=query).json()['revision']==3
    assert (jobs.model(old['candidate_id']).root/'model.json').read_bytes()==manifest
    assert client.get('/publications/'+old['id']+'/api/objects').json()==publication



def test_relation_mapping_authorization_and_old_publication_unchanged(secured):
    rp,client,_,_,jobs,directory,spaces,_,old,new=secured
    headers,_=sign_in(secured,'usr_engineer')
    query={'space_id':spaces[0]['id'],'candidate_id':new['candidate_id']}
    initial=client.get(PATH,params=query).json()
    assert initial['relations'][0]['type_id']=='contains'
    scope=json.dumps([rp.config.issuer,'org_mock','ws_mock'],separators=(',',':'))
    ref=publish_core(directory.root,scope)
    common={**query,'source_sha256':initial['source_sha256']}
    before=client.get('/publications/'+new['id']+'/api/objects').json()
    for revision,(object_id,concept) in enumerate([('room-a','spatial_region'),('cabinet-a','physical_object')]):
        response=client.post(PATH,headers=headers,json={**common,'action':'set','object_id':object_id,
            'reference':ref,'concept_id':concept,'expected_revision':revision,'request_id':str(revision+1)*32})
        assert response.status_code==200,response.text
    # Original contains direction is room -> cabinet. part_of deliberately
    # demonstrates a semantic mismatch; neither direction nor name is inferred.
    body={**common,'action':'relation_set','relation_id':'rel-1','reference':ref,'definition_id':'part_of','direction':'forward',
          'expected_revision':2,'request_id':'a'*32,'valid_time':{'start':'2026-11-20T00:00:00Z','end':None},'evidence_note':'manual fixture'}
    assert client.post(PATH,json=body).status_code==403
    forged={**body,'epistemic_status':'corroborated'}
    assert client.post(PATH,headers=headers,json=forged).status_code==422
    assert client.post(PATH,headers=headers,json=body).status_code==200
    saved=client.get(PATH,params=query).json()
    assert saved['relation_links'][0]['epistemic_status']=='reported'
    assert saved['relation_links'][0]['source_id']=='room-a'
    assert not saved['relation_report']['valid']
    assert any(issue['code']=='endpoint_type_mismatch' for issue in saved['relation_report']['diagnostics'])
    assert client.post(PATH,headers=headers,json=body).json()['revision']==3
    viewer,_=sign_in(secured,'usr_local_test')
    assert client.get(PATH,params=query).status_code==200
    assert client.post(PATH,headers=viewer,json=body).status_code==403
    assert client.get('/publications/'+new['id']+'/api/objects').json()==before
