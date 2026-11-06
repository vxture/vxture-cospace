"""R2b synthetic state/time gate. No real device authorization or trust bootstrap."""
from contextlib import contextmanager
from dataclasses import dataclass
import math
import os
from pathlib import Path
import sqlite3
import uuid

from experiments.scripts.trust_proof import verify, ProofError, decode
from packages.data.imports import canonical, sha
from packages.infrastructure.files import safe_path
from packages.service.sample import read_json
from packages.views.agent.local import LocalSession


class GateError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class IntervalClock:
    """Test anchor only. Counter must include suspend; never reads wall clock."""
    def __init__(self, counter, anchor=None):
        self.counter = counter
        self.anchor = anchor  # (boot, monotonic_tick, earliest_utc, latest_utc)
        self.last = anchor[1] if anchor else None
        self.invalid = False

    def read(self):
        boot, tick = self.counter()
        if self.invalid or self.anchor is None:
            raise GateError('validity_unknown')
        origin_boot, origin, earliest, latest = self.anchor
        if (boot != origin_boot or type(tick) not in (float, int) or not math.isfinite(tick)
                or tick < self.last or not all(type(v) in (int, float) and math.isfinite(v) for v in (origin, earliest, latest))
                or earliest > latest):
            self.invalid = True
            raise GateError('validity_unknown')
        self.last = tick
        return earliest + tick - origin, latest + tick - origin


@dataclass(frozen=True)
class Policy:
    audience: str
    deployment: str
    max_offline: int
    key_not_before: int
    key_expires: int
    epoch: int = 1

    def __post_init__(self):
        if (not self.audience or not self.deployment or type(self.max_offline) is not int or self.max_offline <= 0
                or type(self.epoch) is not int or self.epoch < 1
                or type(self.key_not_before) is not int or type(self.key_expires) is not int
                or not 0 <= self.key_not_before < self.key_expires):
            raise GateError('invalid_policy')

    def digest(self):
        return sha(canonical(vars(self)))


class ValidityStore:
    def __init__(self, root, trust, policy, *, bootstrap=False):
        self.root = safe_path(root)
        self.path = safe_path(self.root / 'validity-test.sqlite3')
        self.pending = safe_path(self.root / 'pending')
        # Snapshot caller configuration; test registry has no delegated root authority.
        self.trust, self.policy = dict(trust), policy
        self.storage_fault = False
        fingerprint = sha(canonical({'policy': vars(policy), 'trust': {
            kid: {'key': key.public_key.hex(), 'issuer': key.issuer, 'deployment': key.deployment_id, 'roles': sorted(key.roles),
                  'not_before': key.not_before, 'expires_at': key.expires_at, 'scenes': key.scenes, 'revoked': key.revoked}
            for kid, key in sorted(trust.items())}}))
        if bootstrap:
            self.root.mkdir(parents=True, exist_ok=True)
            # Explicit bootstrap never overwrites a pre-existing store or lost-state sentinel.
            with self.path.open('xb'):
                pass
            with self._db() as db:
                db.executescript('CREATE TABLE config (fingerprint TEXT NOT NULL); CREATE TABLE states (identity TEXT PRIMARY KEY,binding BLOB NOT NULL,content TEXT,status TEXT,grant_proof TEXT,revoked BLOB NOT NULL);')
                db.execute('INSERT INTO config VALUES (?)', (fingerprint,))
        if not self.path.is_file():
            raise GateError('validity_unknown')
        with self._db() as db:
            if db.execute('SELECT fingerprint FROM config').fetchone() != (fingerprint,):
                raise GateError('trust_context_changed')

    @contextmanager
    def _db(self):
        # mode=rw refuses recreation after deletion.
        db = sqlite3.connect(safe_path(self.path).as_uri() + '?mode=rw', uri=True, timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _before_commit(self):
        """Fault barrier; no-op outside tests."""

    def _decision_snapshot(self):
        """Test barrier after selecting a database snapshot."""

    def _pending_exists(self):
        safe_path(self.pending)
        return self.pending.exists() and any(self.pending.iterdir())

    def _identity(self, binding):
        return sha(canonical([self.policy.deployment, binding['scene_id'], binding['package_sha256']]))

    def _proof(self, token, kind, binding):
        try:
            result = verify(token, self.trust, expected_kind=kind, expected_deployment=self.policy.deployment,
                            expected_binding=binding, expected_audience=self.policy.audience)
        except ProofError as error:
            raise GateError('invalid_proof') from error
        issued = result['document']['issued_at']
        key = self.trust[read_json(decode(token.split('.')[0]))['kid']]
        if key.revoked or (key.scenes and binding['scene_id'] not in key.scenes):
            raise GateError('key_scope_or_revocation')
        if not max(self.policy.key_not_before, key.not_before) <= issued < min(self.policy.key_expires, key.expires_at):
            raise GateError('key_interval_mismatch')
        result['key_interval'] = [key.not_before, key.expires_at]
        return result

    def accept(self, binding, token, kind):
        if self.storage_fault:
            raise GateError('storage_error')
        # Validate untrusted input before creating a durable intent.
        self._proof(token, kind, binding)
        try:
            self.pending.mkdir(parents=True, exist_ok=True)
            marker = safe_path(self.pending / (uuid.uuid4().hex + '.json'))
            with marker.open('xb') as stream:
                stream.write(canonical({'kind': kind, 'token_sha256': sha(token.encode('ascii'))}))
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            self.storage_fault = True
            raise
        try:
            result = self._accept(binding, token, kind)
            marker.unlink()
            return result
        except (sqlite3.Error, OSError):
            self.storage_fault = True
            raise
        except Exception:
            marker.unlink()
            raise

    def _accept(self, binding, token, kind):
        proof = self._proof(token, kind, binding)
        doc, body = proof['document'], proof['document']['body']
        identity = self._identity(binding)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("INSERT OR IGNORE INTO states VALUES (?,?,NULL,NULL,NULL,?)", (identity, canonical(binding), canonical([])))
            row = db.execute('SELECT binding,content,status,grant_proof,revoked FROM states WHERE identity=?', (identity,)).fetchone()
            if row[0] != canonical(binding):
                raise GateError('binding_conflict')
            if kind == 'content_statement':
                db.execute('UPDATE states SET content=? WHERE identity=?', (token, identity))
            elif kind == 'status_snapshot':
                if body['epoch'] != self.policy.epoch:
                    raise GateError('epoch_not_authorized')
                old = self._proof(row[2], kind, binding) if row[2] else None
                if old:
                    old_body = old['document']['body']
                    if body['sequence'] < old_body['sequence']:
                        raise GateError('state_rollback')
                    if body['sequence'] == old_body['sequence']:
                        if proof['payload_sha256'] != old['payload_sha256']:
                            raise GateError('state_conflict')
                        return {'accepted': True, 'idempotent': True, 'authorized': False}
                revoked = set(read_json(row[4]))
                if any(c['name'] in revoked and c['state'] != 'revoked' for c in body['capabilities']):
                    raise GateError('revocation_terminal')
                revoked.update(c['name'] for c in body['capabilities'] if c['state'] == 'revoked')
                db.execute('UPDATE states SET status=?,grant_proof=NULL,revoked=? WHERE identity=?', (token, canonical(sorted(revoked)), identity))
            elif kind == 'capability_grant':
                if not row[2]:
                    raise GateError('status_missing')
                state = self._proof(row[2], 'status_snapshot', binding)
                expected = {'epoch': state['document']['body']['epoch'], 'sequence': state['document']['body']['sequence'], 'payload_sha256': state['payload_sha256']}
                if body['status'] != expected or body['policy_sha256'] != self.policy.digest():
                    raise GateError('grant_status_mismatch')
                if doc['issued_at'] < state['document']['issued_at']:
                    raise GateError('grant_predates_status')
                if row[3] and self._proof(row[3], kind, binding)['payload_sha256'] != proof['payload_sha256']:
                    raise GateError('grant_requires_new_state')
                db.execute('UPDATE states SET grant_proof=? WHERE identity=?', (token, identity))
            else:
                raise GateError('unsupported_kind')
            self._before_commit()
        return {'accepted': True, 'idempotent': False, 'authorized': False}

    def decide(self, binding, capability, clock):
        try:
            if self.storage_fault or self._pending_exists():
                raise GateError('storage_error')
            return self._decide(binding, capability, clock)
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as error:
            if isinstance(error, (sqlite3.Error, OSError)):
                self.storage_fault = True
            code = error.code if isinstance(error, GateError) else 'storage_error'
            return {'simulated_allowed': False, 'reason': code, 'authorized': False, 'robot_ready': False}

    def _decide(self, binding, capability, clock):
        with self._db() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT binding,content,status,grant_proof,revoked FROM states WHERE identity=?', (self._identity(binding),)).fetchone()
            self._decision_snapshot()
            if row is None or row[0] != canonical(binding) or not row[1] or not row[2]:
                raise GateError('validity_unknown')
            content = self._proof(row[1], 'content_statement', binding)
            status = self._proof(row[2], 'status_snapshot', binding)
            body = status['document']['body']
            if body['epoch'] != self.policy.epoch:
                raise GateError('epoch_not_authorized')
            if capability in read_json(row[4]):
                raise GateError('revoked')
            entry = next((c for c in body['capabilities'] if c['name'] == capability), None)
            if entry is None:
                raise GateError('capability_not_granted')
            if entry['state'] != 'allowed':
                raise GateError(entry['state'])
            if not row[3]:
                raise GateError('grant_missing')
            grant = self._proof(row[3], 'capability_grant', binding)
            g = grant['document']['body']
            if g['status'] != {'epoch': body['epoch'], 'sequence': body['sequence'], 'payload_sha256': status['payload_sha256']} or g['policy_sha256'] != self.policy.digest():
                raise GateError('grant_status_mismatch')
            if capability not in g['capabilities']:
                raise GateError('capability_not_granted')
            earliest, latest = clock.read()
            key_intervals = [p['key_interval'] for p in (content, status, grant)]
            start = max(g['not_before'], status['document']['issued_at'], content['document']['issued_at'], self.policy.key_not_before,
                        grant['document']['issued_at'], *(i[0] for i in key_intervals))
            # Conservative: offline budget starts at signed status time, never receipt time.
            end = min(g['expires_at'], body['expires_at'], self.policy.key_expires, *(i[1] for i in key_intervals),
                      status['document']['issued_at'] + min(g['max_offline_seconds'], self.policy.max_offline))
            if latest < start:
                raise GateError('not_yet_valid')
            if earliest >= end:
                raise GateError('expired')
            if earliest < start or latest >= end:
                raise GateError('validity_unknown')
            return {'simulated_allowed': True, 'reason': 'synthetic_conditions_met', 'authorized': False,
                    'robot_ready': False, 'sequence': body['sequence'], 'epoch': body['epoch'],
                    'time_interval': [earliest, latest], 'deadline': end}


class GuardedSession:
    def __init__(self, files, scene, ledger, binding, clock):
        self.ledger, self.binding, self.clock = ledger, read_json(canonical(binding)), clock
        self.closed = False
        with files._connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT digest,revision FROM active WHERE scene=?', (scene,)).fetchone()
            if not row or row[0] != binding['package_sha256']:
                raise GateError('active_package_mismatch')
            manifest, members = files._load(db, row[0])
            source = manifest['source']
            expected = {k: source[k] for k in ('scene_id','release_id','truth_version_id','view_version_id','release_sha256','truth_sha256','view_sha256')}
            expected.update(package_sha256=row[0], profile=manifest['profile'], scope_sha256=sha(canonical(manifest['scope'])))
            if expected != binding:
                raise GateError('binding_conflict')
            self.session = LocalSession(manifest, members, row[1])
        if not ledger.decide(binding, 'synthetic_point_query', clock)['simulated_allowed']:
            self.session.close()
            raise GateError('session_not_allowed')

    def query(self, point):
        if self.closed:
            raise GateError('session_closed')
        decision = self.ledger.decide(self.binding, 'synthetic_point_query', self.clock)
        if not decision['simulated_allowed']:
            raise GateError(decision['reason'])
        return {**self.session.query(point), 'gate': decision}

    def close(self):
        self.closed = True
        self.session.close()
