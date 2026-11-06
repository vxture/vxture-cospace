"""R2a test-only proofs: RFC 8032 vectors, original JWS bytes and rejection."""
import base64
import copy
import json
import secrets
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from experiments.scripts.trust_proof import (ProofError, b64, limited_json, load_test_trust,
                                            native_crypto, verify, SCHEMA)
from packages.data.imports import canonical, sha


# RFC 8032 section 7.1, TEST 1 and TEST 2. Public reproducible vectors, not credentials.
VECTORS = [
 ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60',
  'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
  'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
 ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb',
  '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
  '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00')]


def native_sign(seed, raw):
    return native_crypto({'operation': 'sign-test', 'seed': seed, 'message': base64.b64encode(raw).decode()})


@pytest.mark.parametrize('seed,pub,message,signature', VECTORS)
def test_rfc8032_vectors(seed, pub, message, signature):
    raw = bytes.fromhex(message)
    signed = native_sign(seed, raw)
    assert signed == {'public_key': pub, 'signature': signature}
    request = {'operation': 'verify', 'public_key': pub, 'signature': signature, 'message': base64.b64encode(raw).decode()}
    assert native_crypto(request)['valid']
    request['message'] = base64.b64encode(raw + b'x').decode()
    assert not native_crypto(request)['valid']


@pytest.fixture
def setup():
    # Private test seed stays in process memory and is never written to fixtures/evidence.
    seed = secrets.token_hex(32)
    pub = native_sign(seed, b'')['public_key']
    trust_doc = {'schema_version': 'cospace.test-trust/0.1', 'test_only': True,
                 'deployment_id': 'test-deployment', 'keys': [
                     {'kid': 'test-publisher', 'issuer': 'test-issuer', 'public_key_hex': pub, 'roles': ['publisher']},
                     {'kid': 'test-validity', 'issuer': 'test-issuer', 'public_key_hex': pub, 'roles': ['validity']}]}
    trust = load_test_trust(canonical(trust_doc))
    path = Path('examples/agent-runtime/agent-package.json')
    manifest = json.loads(path.read_text())
    source = manifest['source']
    binding = {key: source[key] for key in ('scene_id', 'release_id', 'truth_version_id', 'view_version_id', 'release_sha256', 'truth_sha256', 'view_sha256')}
    binding.update(package_sha256=sha(path.read_bytes()), profile=manifest['profile'], scope_sha256=sha(canonical(manifest['scope'])))
    doc = {'schema_version': 'cospace.trust-proof/0.1', 'kind': 'content_statement',
           'issuer': 'test-issuer', 'deployment_id': 'test-deployment', 'data_kind': 'synthetic',
           'binding': binding, 'issued_at': 100, 'body': {'package_schema': 'cospace.agent-package/0.1'}}
    return seed, trust_doc, trust, doc


def token(seed, doc, kid='test-publisher', header=None, raw=None):
    protected = b64(canonical(header or {'alg': 'EdDSA', 'typ': 'cospace-test-proof+jws', 'kid': kid, 'version': '0.1'}))
    payload = b64(canonical(doc) if raw is None else raw)
    signing = (protected + '.' + payload).encode()
    return protected + '.' + payload + '.' + b64(bytes.fromhex(native_sign(seed, signing)['signature']))


def check(setup, proof, kind='content_statement', **kwargs):
    _, _, trust, doc = setup
    return verify(proof, trust, expected_kind=kind, expected_deployment='test-deployment', expected_binding=doc['binding'],
                  expected_audience='test-device' if kind != 'content_statement' else None, **kwargs)


@pytest.mark.parametrize('kind', ['content_statement', 'capability_grant', 'status_snapshot'])
def test_three_proof_kinds_are_never_authorization(setup, kind):
    seed, _, _, original = setup
    doc = copy.deepcopy(original)
    doc['kind'] = kind
    if kind == 'capability_grant':
        doc['body'] = {'audience': 'test-device', 'capabilities': ['synthetic_point_query'], 'policy_sha256': 'a'*64,
                       'status': {'epoch': 1, 'sequence': 1, 'payload_sha256': 'b'*64},
                       'not_before': 100, 'expires_at': 200, 'max_offline_seconds': 60}
    elif kind == 'status_snapshot':
        doc['body'] = {'epoch': 1, 'sequence': 1, 'audience': 'test-device', 'expires_at': 200,
                       'capabilities': [{'name': 'synthetic_point_query', 'state': 'allowed', 'reason': 'test only'}]}
    result = check(setup, token(seed, doc, 'test-publisher' if kind == 'content_statement' else 'test-validity'), kind)
    assert result['proof_verified'] and not result['authorized'] and not result['robot_ready']


def test_whitespace_signature_original_bytes_and_tampering(setup):
    seed, _, _, doc = setup
    raw = json.dumps(doc, indent=3).encode()
    proof = token(seed, doc, raw=raw)
    assert check(setup, proof)['payload_sha256'] == sha(raw)
    segments = proof.split('.')
    segments[1] = b64(canonical(doc))  # Same object, different signed bytes.
    with pytest.raises(ProofError, match='signature'):
        check(setup, '.'.join(segments))
    segments = proof.split('.')
    segments[2] = b64(b'\0' * 64)
    with pytest.raises(ProofError):
        check(setup, '.'.join(segments))


@pytest.mark.parametrize('change', [
    lambda d: d.update(issuer='other'), lambda d: d.update(deployment_id='other'),
    lambda d: d['binding'].update(package_sha256='0'*64), lambda d: d['binding'].update(scope_sha256='0'*64),
    lambda d: d['binding'].update(view_version_id='other'), lambda d: d.update(data_kind='real'),
    lambda d: d.update(schema_version='cospace.trust-proof/9'), lambda d: d['body'].update(unexpected=True),
])
def test_signed_but_wrong_context_rejected(setup, change):
    seed, _, _, original = setup
    doc = copy.deepcopy(original)
    change(doc)
    with pytest.raises(ProofError):
        check(setup, token(seed, doc))


@pytest.mark.parametrize('change', [lambda h: h.update(alg='none'), lambda h: h.update(alg='HS256'),
    lambda h: h.update(jku='https://untrusted.invalid/key'), lambda h: h.update(crit=['unknown']),
    lambda h: h.update(kid='unknown'), lambda h: h.update(version='9')])
def test_header_rejections(setup, change):
    seed, _, _, doc = setup
    header = {'alg': 'EdDSA', 'typ': 'cospace-test-proof+jws', 'kid': 'test-publisher', 'version': '0.1'}
    change(header)
    with pytest.raises(ProofError):
        check(setup, token(seed, doc, header=header))


def test_wrong_role_and_self_supplied_key_rejected(setup):
    seed, trust_doc, _, doc = setup
    with pytest.raises(ProofError, match='role'):
        check(setup, token(seed, doc, kid='test-validity'))
    doc = copy.deepcopy(doc)
    doc['body']['public_key'] = trust_doc['keys'][0]['public_key_hex']
    with pytest.raises(ProofError):
        check(setup, token(seed, doc, kid='new-self-key'))
    trust_doc['keys'].append(copy.deepcopy(trust_doc['keys'][0]))
    with pytest.raises(ProofError, match='duplicate'):
        load_test_trust(canonical(trust_doc))


def test_duplicate_keys_depth_limits_and_bad_encoding(setup):
    seed, _, _, doc = setup
    with pytest.raises(ProofError, match='JSON'):
        check(setup, token(seed, doc, raw=b'{"kind":1,"kind":2}'))
    with pytest.raises(ProofError, match='nesting'):
        check(setup, token(seed, doc, raw=b'['*13 + b'0' + b']'*13))
    with pytest.raises(ProofError):
        limited_json(b'\xff')
    for proof in ('x'*50000, 'A.eA.eA', 'e30=.e30.e30', 'a.b.c.d'):
        with pytest.raises(ProofError):
            check(setup, proof)


def test_schemas_valid():
    for path in (SCHEMA, SCHEMA.with_name('test-trust-v0.1.schema.json')):
        Draft202012Validator.check_schema(json.loads(path.read_text()))


@pytest.mark.parametrize('change', [lambda b: b.update(audience='other-device'),
    lambda b: b.update(expires_at=100), lambda b: b.update(epoch=True),
    lambda b: b['capabilities'].append(copy.deepcopy(b['capabilities'][0]))])
def test_status_audience_interval_counter_and_duplicates(setup, change):
    seed, _, _, original = setup
    doc = copy.deepcopy(original)
    doc['kind'] = 'status_snapshot'
    doc['body'] = {'epoch': 1, 'sequence': 1, 'audience': 'test-device', 'expires_at': 200,
                   'capabilities': [{'name': 'synthetic_point_query', 'state': 'allowed', 'reason': 'test only'}]}
    change(doc['body'])
    with pytest.raises(ProofError):
        check(setup, token(seed, doc, kid='test-validity'), 'status_snapshot')


def test_untrusted_signer_cannot_reuse_known_kid(setup):
    _, _, _, doc = setup
    with pytest.raises(ProofError, match='signature'):
        check(setup, token(secrets.token_hex(32), doc))
