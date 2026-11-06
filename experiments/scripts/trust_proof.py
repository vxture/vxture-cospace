"""R2a synthetic JWS verification probe. No clock, delegation or authorization."""
import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from packages.data.structure import LiteralIntegerValidator
from packages.service.sample import read_json

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/schemas/trust-proof-v0.1.schema.json'
MAX_TOKEN = 49152
MAX_JSON = 32768
ROLES = {'content_statement': 'publisher', 'capability_grant': 'validity', 'status_snapshot': 'validity'}
BRIDGE = Path(__file__).with_name('ed25519_probe.mjs')


class ProofError(ValueError):
    pass


def native_crypto(request):
    result = subprocess.run(['node', str(BRIDGE)], input=json.dumps(request),
                            capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise ProofError('native crypto probe failed')
    return json.loads(result.stdout)


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def decode(value):
    if not value or not re.fullmatch('[A-Za-z0-9_-]+', value):
        raise ProofError('invalid base64url')
    try:
        raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    except binascii.Error as error:
        raise ProofError('invalid base64url length') from error
    if b64(raw) != value:
        raise ProofError('noncanonical base64url')
    return raw


def limited_json(raw):
    if len(raw) > MAX_JSON:
        raise ProofError('JSON size limit')
    # Bound nesting before recursive JSON decoding; ignore braces inside strings.
    depth, quoted, escaped = 0, False, False
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise ProofError('invalid UTF-8') from error
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > 12:
                raise ProofError('JSON nesting limit')
        elif char in ']}':
            depth -= 1
    try:
        return read_json(raw)
    except (ValueError, RecursionError) as error:
        raise ProofError('invalid JSON: ' + str(error)) from error


@dataclass(frozen=True)
class TestTrust:
    """Explicit caller-provided test trust; never extracted from message payload."""
    public_key: bytes
    issuer: str
    deployment_id: str
    roles: frozenset
    not_before: int = 0
    expires_at: int = 253402300799
    scenes: tuple = ()
    revoked: bool = False


def load_test_trust(raw):
    document = limited_json(raw)
    schema = json.loads(SCHEMA.with_name('test-trust-v0.1.schema.json').read_text(encoding='utf-8'))
    if next(LiteralIntegerValidator(schema).iter_errors(document), None) is not None:
        raise ProofError('test trust structure rejected')
    trust = {}
    for key in document['keys']:
        if key['kid'] in trust:
            raise ProofError('duplicate test kid')
        trust[key['kid']] = TestTrust(bytes.fromhex(key['public_key_hex']), key['issuer'], document['deployment_id'], frozenset(key['roles']))
    return trust


def verify(token, trust, *, expected_kind, expected_deployment, expected_binding, expected_audience=None):
    if expected_kind not in ROLES:
        raise ProofError('unsupported expected kind')
    if not isinstance(token, str) or len(token) > MAX_TOKEN or token.count('.') != 2:
        raise ProofError('compact JWS size or structure')
    protected, payload, signature = token.split('.')
    header = limited_json(decode(protected))
    if (not isinstance(header, dict) or set(header) != {'alg', 'typ', 'kid', 'version'}
            or header.get('alg') != 'EdDSA' or header.get('typ') != 'cospace-test-proof+jws'
            or header.get('version') != '0.1' or not isinstance(header.get('kid'), str)
            or not 1 <= len(header['kid']) <= 128):
        raise ProofError('unsupported protected header')
    key = trust.get(header['kid'])
    if not isinstance(key, TestTrust):
        raise ProofError('unknown test key')
    sig = decode(signature)
    if len(sig) != 64 or len(key.public_key) != 32:
        raise ProofError('invalid Ed25519 key or signature length')
    # Verify ORIGINAL encoded segments, never reserialize to verify a signature.
    try:
        message = (protected + '.' + payload).encode('ascii')
    except UnicodeError as error:
        raise ProofError('non-ASCII compact JWS') from error
    checked = native_crypto({'operation': 'verify', 'public_key': key.public_key.hex(),
                             'signature': sig.hex(), 'message': base64.b64encode(message).decode('ascii')})
    if not checked['valid']:
        raise ProofError('signature verification failed')
    raw = decode(payload)
    document = limited_json(raw)
    validator = LiteralIntegerValidator(json.loads(SCHEMA.read_text(encoding='utf-8')))
    if next(validator.iter_errors(document), None) is not None:
        raise ProofError('payload structure rejected')
    if document['kind'] != expected_kind or ROLES[expected_kind] not in key.roles:
        raise ProofError('kind or signing role mismatch')
    if document['issuer'] != key.issuer or document['deployment_id'] != expected_deployment or key.deployment_id != expected_deployment:
        raise ProofError('issuer or deployment mismatch')
    if document['binding'] != expected_binding:
        raise ProofError('fixed package binding mismatch')
    body = document['body']
    if expected_kind != 'content_statement':
        if not expected_audience or body['audience'] != expected_audience:
            raise ProofError('audience mismatch')
        if body['expires_at'] <= document['issued_at']:
            raise ProofError('invalid validity interval')
    if expected_kind == 'capability_grant' and not document['issued_at'] <= body['not_before'] < body['expires_at']:
        raise ProofError('invalid grant interval')
    if expected_kind == 'status_snapshot':
        names = [item['name'] for item in body['capabilities']]
        if len(set(names)) != len(names):
            raise ProofError('duplicate capability name')
    return {'proof_verified': True, 'authorized': False, 'robot_ready': False,
            'payload_sha256': hashlib.sha256(raw).hexdigest(), 'document': document,
            'not_checked': ['delegation', 'key_validity', 'trusted_time', 'status_high_water', 'revocation', 'grant_status_relation']}
