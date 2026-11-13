from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3
import pytest
from pydantic import ValidationError
from packages.service.service_recipients import ServiceRecipients, RecipientChange, RecipientConflict, RecipientsUnavailable
from packages.service.space_access import SpaceAccessPolicy
from packages.infrastructure.platform_identity import PlatformPrincipal
from test_platform_business import secured, sign_in
from test_platform_login import runtime

A, B = 'space-'+'a'*16, 'space-'+'b'*16
SPACES = [{'id': A, 'name': 'A'}, {'id': B, 'name': 'B'}]
PRINCIPAL = PlatformPrincipal('https://accounts.example', 'usr_manager', 'org_1', 'ws_1', (), 'Manager', 1800000000)


def policy():
    return SpaceAccessPolicy.model_validate({'bindings': [dict(issuer=PRINCIPAL.issuer, org_id='org_1', workspace_id='ws_1', space_id=s) for s in (A, B)],
        'grants': [dict(issuer=PRINCIPAL.issuer, subject=PRINCIPAL.subject, space_id=s, role='manager') for s in (A, B)]})


def body(space=A, **overrides):
    return dict(request_id='a'*32, expected_revision=0, name='设备 01', morphology='quadruped',
        relations=[dict(space_id=space, purposes=['collect','use'], usage_modes=['online','offline'])]) | overrides


def test_store_restart_idempotency_cas_history_and_tenant_isolation(tmp_path):
    store = ServiceRecipients(tmp_path)
    assert store.list(PRINCIPAL, policy(), SPACES)['total'] == 0
    assert not store.path.exists()
    change = RecipientChange.model_validate(body())
    first = store.save(PRINCIPAL, policy(), SPACES, change)
    assert store.save(PRINCIPAL, policy(), SPACES, change) == first
    with pytest.raises(RecipientConflict):
        store.save(PRINCIPAL, policy(), SPACES, change.model_copy(update={'name':'different'}))
    restarted = ServiceRecipients(tmp_path)
    assert restarted.list(PRINCIPAL, policy(), SPACES)['recipients'][0]['id'] == first['id']
    for user in (replace(PRINCIPAL, workspace_id='ws_2'), replace(PRINCIPAL, org_id='org_2'), replace(PRINCIPAL, issuer='https://foreign.example')):
        assert restarted.list(user, policy(), SPACES)['total'] == 0
        with pytest.raises(PermissionError):
            restarted.save(user, policy(), SPACES, change)
    updated = change.model_copy(update={'request_id':'b'*32,'expected_revision':1,'name':'renamed','relations':[]})
    result = restarted.save(PRINCIPAL, policy(), SPACES, updated, first['id'])
    assert result['id'] == first['id'] and result['revision'] == 2
    assert restarted.list(PRINCIPAL, policy(), SPACES)['total'] == 1
    with pytest.raises(RecipientConflict):
        restarted.save(PRINCIPAL, policy(), SPACES, updated.model_copy(update={'request_id':'c'*32}), first['id'])
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT COUNT(*) FROM recipient_history').fetchone()[0] == 2


def test_per_space_visibility_does_not_leak_relations_or_allow_shared_edits(tmp_path):
    store = ServiceRecipients(tmp_path)
    both = body(relations=[dict(space_id=A,purposes=['collect']),dict(space_id=B,purposes=['use'])])
    saved = store.save(PRINCIPAL, policy(), SPACES, RecipientChange.model_validate(both))
    value = policy().model_dump();value['grants'] = value['grants'][:1]
    limited = SpaceAccessPolicy.model_validate(value)
    result = store.list(PRINCIPAL, limited, SPACES)
    assert [r['space_id'] for r in result['recipients'][0]['relations']] == [A]
    assert not result['recipients'][0]['can_manage']
    assert store.list(PRINCIPAL, limited, SPACES, purpose='use')['total'] == 0
    with pytest.raises(PermissionError):
        store.list(PRINCIPAL, limited, SPACES, space_id=B)
    with pytest.raises(PermissionError):
        store.save(PRINCIPAL, limited, SPACES, RecipientChange.model_validate(body(request_id='b'*32, expected_revision=1)), saved['id'])


def test_concurrent_edit_has_one_winner(tmp_path):
    saved = ServiceRecipients(tmp_path).save(PRINCIPAL, policy(), SPACES, RecipientChange.model_validate(body()))
    def save(key):
        try:
            change = RecipientChange.model_validate(body(request_id=key*32,expected_revision=1,name=key))
            return ServiceRecipients(tmp_path).save(PRINCIPAL, policy(), SPACES, change, saved['id'])['revision']
        except RecipientConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(map(str, pool.map(save, ['b','c']))) == ['2','conflict']


@pytest.mark.parametrize('form',['aerial','quadruped','wheeled','tracked','humanoid','other'])
@pytest.mark.parametrize('purposes',[['collect'],['use'],['collect','use']])
def test_every_morphology_supports_independent_purposes(tmp_path, form, purposes):
    change = RecipientChange.model_validate(body(morphology=form,morphology_note='复合形态' if form=='other' else '',
        relations=[dict(space_id=A,purposes=purposes)]))
    result = ServiceRecipients(tmp_path).save(PRINCIPAL, policy(), SPACES, change)
    assert result['relations'][0]['purposes'] == sorted(purposes)


@pytest.mark.parametrize('overrides',[{'name':' '},{'morphology':'robot'},{'morphology':'other'}, {'expected_revision':True},
    {'relations':[dict(space_id=A,purposes=[])]}, {'relations':[dict(space_id=A,purposes=['collect'],usage_modes=['online'])]},
    {'relations':[dict(space_id=A,purposes=['use','use'])]}, {'token':'secret'}])
def test_invalid_registration_rejected(overrides):
    with pytest.raises(ValidationError):
        RecipientChange.model_validate(body(**overrides))


def test_owner_without_spaces_can_register_but_no_implicit_binding(tmp_path):
    owner = replace(PRINCIPAL, governance_roles=('workspace:owner',))
    store = ServiceRecipients(tmp_path)
    saved = store.save(owner, policy(), [], RecipientChange.model_validate(body(relations=[])))
    result = store.list(owner, policy(), [])
    assert result['can_create'] and result['recipients'][0]['relations'] == []
    assert result['recipients'][0]['integration_state'] == 'pending'
    assert not result['recipients'][0]['external_identity_verified']
    assert 'token' not in saved


def test_corrupt_store_fails_closed(tmp_path):
    store = ServiceRecipients(tmp_path);store.path.write_bytes(b'corrupt')
    with pytest.raises(RecipientsUnavailable):
        store.list(PRINCIPAL, policy(), SPACES)


def test_unassigned_registration_is_not_visible_to_unrelated_manager(tmp_path):
    store = ServiceRecipients(tmp_path)
    store.save(PRINCIPAL, policy(), SPACES, RecipientChange.model_validate(body(relations=[])))
    other = replace(PRINCIPAL, subject='usr_other')
    value = policy().model_dump()
    value['grants'] = [g | {'subject':'usr_other'} for g in value['grants']]
    assert store.list(other, SpaceAccessPolicy.model_validate(value), SPACES)['total'] == 0
    assert store.list(replace(other, governance_roles=('workspace:owner',)), policy(), SPACES)['total'] == 1


def test_http_revocation_invalid_routes_and_corrupt_storage(secured):
    _, client, _, _, _, directory, spaces, policies, *_ = secured
    headers, _ = sign_in(secured,'usr_manager')
    saved = client.post('/api/service-recipients',json=body(spaces[0]['id']),headers=headers).json()
    assert client.get('/api/service-recipients/'+saved['id']).status_code == 403
    assert client.put('/api/service-recipients/'+saved['id'],json={},headers=headers).status_code == 403
    revision, current = policies.load(); value = current.model_dump()
    value['grants'] = [g for g in value['grants'] if g['subject'] != 'usr_manager']
    policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=revision,actor='test',reason='revoke')
    assert client.get('/api/service-recipients').json()['total'] == 0
    assert client.post('/api/service-recipients',json=body(spaces[0]['id']),headers=headers).status_code == 403
    sign_in(secured)
    (directory.root/'service-recipients.sqlite3').write_bytes(b'corrupt')
    assert client.get('/api/service-recipients').status_code == 503


def test_http_registration_permissions_csrf_revision_and_no_release_dependency(secured):
    _, client, _, _, jobs, _, spaces, *_ = secured
    identity = spaces[0]['id']
    for user in ('usr_local_test','usr_engineer'):
        headers, _ = sign_in(secured, user)
        assert not client.get('/api/service-recipients').json()['can_create']
        assert client.post('/api/service-recipients',json=body(identity),headers=headers).status_code == 403
    headers, _ = sign_in(secured,'usr_manager')
    assert client.post('/api/service-recipients',json=body(identity)).status_code == 403
    # No service publication is required to register a source device.
    response = client.post('/api/service-recipients',json=body(identity),headers=headers)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['revision'] == 1 and saved['can_manage']
    assert client.post('/api/service-recipients',json=body(identity),headers=headers).json() == saved
    route = '/api/service-recipients/'+saved['id']
    update = body(identity,request_id='b'*32,expected_revision=1,name='Updated',relations=[dict(space_id=identity,purposes=['use'])])
    assert client.patch(route,json=update,headers=headers).status_code == 200
    assert client.patch(route,json=update|{'request_id':'c'*32},headers=headers).status_code == 409
    assert client.post('/api/service-recipients',json=body(spaces[1]['id'],request_id='d'*32),headers=headers).status_code == 403
    assert client.get('/api/service-recipients',params={'space_id':spaces[1]['id']}).status_code == 403
    assert client.get('/api/service-recipients',params={'purpose':'collect'}).json()['total'] == 0
    assert client.get('/api/service-recipients',params={'q':'updated'}).json()['total'] == 1
    assert client.get('/api/service-recipients',params={'limit':'0'}).status_code == 422
    assert client.post('/api/service-recipients',json=body(identity,token='bad'),headers=headers).status_code == 422
    sign_in(secured)
    value = client.get('/api/service-recipients').json()['recipients'][0]
    assert not value['can_manage'] and 'created_by' not in value and 'request_id' not in value
    assert client.patch(route,json=update,headers=headers).status_code == 403
    sign_in(secured,'usr_other')
    assert client.get('/api/service-recipients').json()['total'] == 0
