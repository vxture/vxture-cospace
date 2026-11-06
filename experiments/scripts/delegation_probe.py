"""R2b one-hop test-root delegation. No trust bootstrap, rotation or network."""
import base64
import json

from experiments.scripts.trust_proof import (ProofError, TestTrust, decode, limited_json,
                                            native_crypto, SCHEMA, MAX_TOKEN)
from packages.data.structure import LiteralIntegerValidator


def load_delegation(token, roots, *, expected_deployment, expected_version):
    # Root anchors are preconfigured raw Ed25519 keys, never read from the token.
    if not isinstance(token, str) or len(token) > MAX_TOKEN or token.count('.') != 2:
        raise ProofError('delegation JWS structure')
    protected, payload, signature = token.split('.')
    header = limited_json(decode(protected))
    if (not isinstance(header, dict) or set(header) != {'alg','typ','kid','version'}
            or header.get('alg') != 'EdDSA' or header.get('typ') != 'cospace-test-delegation+jws'
            or header.get('version') != '0.1' or not isinstance(header.get('kid'), str)):
        raise ProofError('delegation protected header')
    root = roots.get(header['kid'])
    sig = decode(signature)
    if not isinstance(root, bytes) or len(root) != 32 or len(sig) != 64:
        raise ProofError('unknown root or invalid signature length')
    valid = native_crypto({'operation':'verify', 'public_key':root.hex(), 'signature':sig.hex(),
                           'message':base64.b64encode((protected+'.'+payload).encode('ascii')).decode('ascii')})
    if not valid['valid']:
        raise ProofError('delegation signature failed')
    doc = limited_json(decode(payload))
    schema = json.loads(SCHEMA.with_name('test-delegation-v0.1.schema.json').read_text(encoding='utf-8'))
    if next(LiteralIntegerValidator(schema).iter_errors(doc), None) is not None:
        raise ProofError('delegation structure rejected')
    if (type(expected_version) is not int or doc['version'] != expected_version
            or doc['deployment_id'] != expected_deployment):
        raise ProofError('delegation context mismatch')
    keys = {}
    for key in doc['keys']:
        if key['kid'] in keys or key['not_before'] >= key['expires_at']:
            raise ProofError('duplicate delegate or invalid interval')
        keys[key['kid']] = TestTrust(bytes.fromhex(key['public_key_hex']), key['issuer'], doc['deployment_id'],
                                    frozenset(key['roles']), key['not_before'], key['expires_at'],
                                    tuple(key['scenes']), key['revoked'])
    return keys
