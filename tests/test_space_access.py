"""Permission rules and saved-resource adapter; HTTP enforcement is a later batch."""
from dataclasses import replace
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from packages.infrastructure.platform_identity import PlatformPrincipal
from packages.service.space_access import SpaceAccessPolicy, CAPABILITIES, ROLE_CAPABILITIES
from packages.service.platform_resource_access import PlatformResourceAccess
from test_preview_workflow import prepared, inventory

ISSUER = 'https://accounts.vxture.com'
A, B = 'space-'+'a'*16, 'space-'+'b'*16


def principal(**changes):
    return replace(PlatformPrincipal(ISSUER, 'usr_alice', 'org_1', 'ws_1', (), 'Alice', 1_800_000_300), **changes)


def policy(spaces=(A, B), role='viewer'):
    return SpaceAccessPolicy.model_validate({
        'bindings': [{'issuer': ISSUER, 'space_id': s, 'org_id': 'org_1', 'workspace_id': 'ws_1'} for s in spaces],
        'grants': [{'issuer': ISSUER, 'subject': 'usr_alice', 'space_id': spaces[0], 'role': role}],
    })


@pytest.mark.parametrize('role', list(ROLE_CAPABILITIES))
@pytest.mark.parametrize('capability', sorted(CAPABILITIES))
def test_product_role_capabilities(role, capability):
    p = policy(role=role)
    if capability in ROLE_CAPABILITIES[role]:
        assert p.require(principal(), A, capability) is None
    else:
        with pytest.raises(PermissionError): p.require(principal(), A, capability)


@pytest.mark.parametrize('changes', [
    {'issuer': 'https://other.example'}, {'subject': 'usr_bob'},
    {'org_id': 'org_2'}, {'workspace_id': 'ws_2'},
])
def test_other_user_issuer_or_active_tenant_cannot_reuse_grant(changes):
    p = policy(role='manager'); user = principal(**changes)
    assert p.visible(user, [{'id': A}, {'id': B}]) == []
    for capability in CAPABILITIES:
        with pytest.raises(PermissionError): p.require(user, A, capability)


def test_multiple_spaces_require_independent_grants():
    p = policy(); user = principal()
    assert p.visible(user, [{'id': A}, {'id': B}]) == [{'id': A}]
    value = p.model_dump(); value['grants'].append(value['grants'][0] | {'space_id': B})
    assert SpaceAccessPolicy.model_validate(value).visible(user, [{'id': A}, {'id': B}]) == [{'id': A}, {'id': B}]
    with pytest.raises(ValueError, match='unknown_space_capability'): p.require(user, A, '*')


@pytest.mark.parametrize('roles', [(), ('admin',), ('owner',), ('org:owner',), ('workspace:manager',)])
def test_governance_roles_do_not_grant_product_owner_except_workspace_owner(roles):
    p = policy(); user = principal(governance_roles=roles)
    assert p.capabilities(user, A) == ROLE_CAPABILITIES['viewer']
    assert p.capabilities(user, B) == frozenset()


def test_workspace_owner_baseline_is_platform_contract_not_persisted_grant():
    p = policy(); user = principal(governance_roles=('workspace:owner',))
    before = p.model_dump()
    # A local viewer grant does not remove the platform's owner baseline.
    assert p.capabilities(user, A) == p.capabilities(user, B) == CAPABILITIES
    assert p.capabilities(user, 'space-'+'c'*16) == frozenset()
    assert p.capabilities(replace(user, workspace_id='ws_other'), A) == frozenset()
    assert p.capabilities(replace(user, org_id='org_other'), A) == frozenset()
    assert p.capabilities(replace(user, issuer='https://other.example'), A) == frozenset()
    assert p.model_dump() == before


@pytest.mark.parametrize('kind', ['duplicate_binding', 'duplicate_grant', 'unbound', 'unknown_role', 'unknown_field'])
def test_invalid_policy_is_rejected(kind):
    value = policy().model_dump()
    if kind == 'duplicate_binding': value['bindings'].append(value['bindings'][0])
    if kind == 'duplicate_grant': value['grants'].append(value['grants'][0])
    if kind == 'unbound': value['grants'][0]['space_id'] = 'space-'+'c'*16
    if kind == 'unknown_role': value['grants'][0]['role'] = 'admin'
    if kind == 'unknown_field': value['grants'][0]['all_spaces'] = True
    with pytest.raises(ValidationError): SpaceAccessPolicy.model_validate(value)


def test_published_policy_schema_and_model_agree():
    schema = json.loads(Path('contracts/schemas/space-access-policy-v0.1.schema.json').read_bytes())
    assert schema == SpaceAccessPolicy.model_json_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(policy().model_dump())


@pytest.fixture
def resource_fixture(tmp_path):
    _, jobs, directory, spaces, _, pubs, old, new = prepared(tmp_path)
    p = policy([s['id'] for s in spaces])
    adapter = PlatformResourceAccess(directory, jobs, p)
    input_id = json.loads((jobs.root/new['candidate_id']/'job.json').read_bytes())['input_id']
    return adapter, spaces, new, input_id


def test_adapter_reads_saved_ownership_without_polling_export_or_source_access(resource_fixture, tmp_path, monkeypatch):
    adapter, spaces, new, input_id = resource_fixture
    def forbidden(*args, **kwargs): pytest.fail('authorization must not poll/export/open geometry or source')
    monkeypatch.setattr(adapter.jobs, 'poll', forbidden)
    monkeypatch.setattr(adapter.jobs, 'model', forbidden)
    monkeypatch.setattr(adapter.jobs.inputs, 'resolve', forbidden)
    monkeypatch.setattr('packages.views.agent.preview_offline.export_bundle', forbidden)
    before = inventory(tmp_path)
    expected = {'space_id': spaces[0]['id'], 'project_id': spaces[0]['project_id']}
    for artifact in ['publication:'+new['id'], 'candidate:'+new['candidate_id'], 'input:'+input_id]:
        assert adapter.artifact(principal(), artifact, 'space.preview') == expected
        with pytest.raises(PermissionError): adapter.artifact(principal(), artifact, 'space.export')
        with pytest.raises(PermissionError): adapter.artifact(principal(subject='usr_bob'), artifact, 'space.preview')
        with pytest.raises(PermissionError): adapter.artifact(principal(), artifact, 'space.preview', requested_space=spaces[1]['id'])
    assert inventory(tmp_path) == before


@pytest.mark.parametrize('kind', ['project', 'id', 'legacy', 'space', 'malformed', 'missing'])
def test_adapter_rejects_forged_saved_ownership(resource_fixture, kind):
    adapter, spaces, new, _ = resource_fixture
    path = adapter.jobs.root/'publications'/new['id']/'publication.json'
    value = json.loads(path.read_bytes())
    if kind == 'project': value['project_id'] = 'project-other'
    if kind == 'id': value['id'] = 'preview-'+'e'*16
    if kind == 'legacy': value.pop('space_id')
    if kind == 'space': value['space_id'] = spaces[1]['id']
    if kind == 'missing': path.unlink()
    else: path.write_text('{' if kind == 'malformed' else json.dumps(value), encoding='utf-8')
    with pytest.raises(PermissionError): adapter.artifact(principal(), 'publication:'+new['id'], 'space.preview')


@pytest.mark.parametrize('artifact', ['../x', 'candidate:../x', 'candidate:build-../x',
    'publication:preview-../../x', 'input:input-../../x', 'offline_package:x', None, 42])
def test_adapter_rejects_invalid_identifiers(resource_fixture, artifact):
    adapter, *_ = resource_fixture
    with pytest.raises(PermissionError): adapter.artifact(principal(), artifact, 'space.preview')
