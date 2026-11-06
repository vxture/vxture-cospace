"""J2 synthetic Windows journal: prepare, atomic state/receipt, no recovery release."""
from contextlib import contextmanager
from dataclasses import dataclass
import re
import sqlite3
import uuid

from experiments.scripts.recovery_lock_probe import StableLock
from experiments.scripts.validity_probe import ValidityStore, GateError
from experiments.scripts.trust_proof import decode, limited_json, MAX_TOKEN
from packages.data.imports import canonical, sha
from packages.infrastructure.files import safe_path
from packages.service.sample import read_json

MAX_COUNTER = 9007199254740991
APP_ID = 1129531186


@dataclass(frozen=True)
class JournalLimits:
    messages: int = 128
    intents: int = 256
    token_bytes: int = 2 * 1024 * 1024
    states: int = 64

    def __post_init__(self):
        for value, maximum in zip(vars(self).values(), (1000, 2000, 32 * 1024 * 1024, 200)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise GateError('invalid_limits')


class JournalStore(ValidityStore):
    """Reuse test proof and time rules; storage/transactions are independent of v1."""
    STORE_VERSION = 2

    def _create_extra(self, db):
        """Optional schema additions for a separate experiment version; never migrate."""
    def _configure(self, root, trust, policy, limits, timeout):
        self.root = safe_path(root)
        self.path = safe_path(self.root / 'journal-test.sqlite3')
        self.lock = StableLock(self.root / 'journal.lock')
        self.trust, self.policy, self.limits = dict(trust), policy, limits
        self.timeout, self.storage_fault = timeout, False
        self.context = sha(canonical({'policy': vars(policy), 'limits': vars(limits), 'trust': {
            kid: {'key': k.public_key.hex(), 'issuer': k.issuer, 'deployment': k.deployment_id,
                  'roles': sorted(k.roles), 'not_before': k.not_before, 'expires_at': k.expires_at,
                  'scenes': k.scenes, 'revoked': k.revoked} for kid, k in sorted(trust.items())}}))

    def __init__(self, root, trust, policy, *, limits=JournalLimits(), timeout=1):
        self._configure(root, trust, policy, limits, timeout)
        with self.lock.hold(timeout) as identity, self._db() as db:
            row = self._control(db, identity, opening=True)
            self.store_id, self.generation = row['store_id'], row['generation']
            self._check_snapshot(db, row)

    @classmethod
    def bootstrap(cls, root, trust, policy, *, limits=JournalLimits(), timeout=1):
        value = cls.__new__(cls)
        value._configure(root, trust, policy, limits, timeout)
        value.root.mkdir(parents=True, exist_ok=False)
        with value.lock.hold(timeout, create=True) as identity:
            with value.path.open('xb'):
                pass
            with value._db() as db:
                db.execute('BEGIN IMMEDIATE')
                statements = [
                    'CREATE TABLE control (singleton INTEGER PRIMARY KEY CHECK(singleton=1), store_id TEXT NOT NULL, context TEXT NOT NULL, generation INTEGER NOT NULL, mode TEXT NOT NULL, revision INTEGER NOT NULL, state_sha256 TEXT NOT NULL, lock_identity TEXT NOT NULL)',
                    'CREATE TABLE messages (digest TEXT PRIMARY KEY, kind TEXT NOT NULL, identity TEXT NOT NULL, binding BLOB NOT NULL, token TEXT NOT NULL)',
                    'CREATE TABLE intents (intent_id TEXT PRIMARY KEY, message_sha256 TEXT NOT NULL REFERENCES messages(digest), generation INTEGER NOT NULL, prepared_revision INTEGER NOT NULL)',
                    'CREATE TABLE receipts (intent_id TEXT PRIMARY KEY REFERENCES intents(intent_id), record BLOB NOT NULL)',
                    'CREATE TABLE states (identity TEXT PRIMARY KEY, binding BLOB NOT NULL, content TEXT, status TEXT, grant_proof TEXT, revoked BLOB NOT NULL)']
                for statement in statements:
                    db.execute(statement)
                value._create_extra(db)
                for table in ('messages', 'intents', 'receipts'):
                    for action in ('UPDATE', 'DELETE'):
                        db.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable journal'); END")
                store_id = str(uuid.uuid4())
                db.execute('INSERT INTO control VALUES (1,?,?,1,?,0,?,?)', (store_id, value.context, 'normal', '', identity))
                value.store_id, value.generation = store_id, 1
                digest = value._snapshot(db, 0)
                db.execute('UPDATE control SET state_sha256=?', (digest,))
                db.execute(f'PRAGMA application_id={APP_ID}')
                db.execute(f'PRAGMA user_version={cls.STORE_VERSION}')
        return cls(root, trust, policy, limits=limits, timeout=timeout)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(safe_path(self.path).as_uri() + '?mode=rw', uri=True, timeout=1)
        db.row_factory = sqlite3.Row
        try:
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4 * 1024 * 1024)
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def _control(self, db, identity, *, opening=False):
        if (db.execute('PRAGMA application_id').fetchone()[0] != APP_ID
                or db.execute('PRAGMA user_version').fetchone()[0] != self.STORE_VERSION):
            raise GateError('unsupported_journal')
        rows = db.execute('SELECT * FROM control LIMIT 2').fetchall()
        if len(rows) != 1:
            raise GateError('invalid_control')
        row = rows[0]
        if (row['singleton'] != 1 or row['context'] != self.context
                or row['mode'] not in ('normal', 'recovering')
                or type(row['revision']) is not int or not 0 <= row['revision'] <= MAX_COUNTER
                or type(row['generation']) is not int or not 1 <= row['generation'] <= MAX_COUNTER):
            raise GateError('context_or_control_changed')
        if row['lock_identity'] != identity:
            raise GateError('lock_identity_changed')
        if not opening and (row['store_id'] != self.store_id or row['generation'] != self.generation):
            raise GateError('stale_generation')
        return row

    def _snapshot(self, db, revision):
        states = []
        rows = db.execute('SELECT * FROM states ORDER BY identity LIMIT ?', (self.limits.states + 1,)).fetchall()
        if len(rows) > self.limits.states:
            raise GateError('state_limit')
        for row in rows:
            binding = read_json(row['binding'])
            if row['identity'] != self._identity(binding):
                raise GateError('state_identity_mismatch')
            for key in ('content', 'status', 'grant_proof'):
                if row[key] is not None and (not isinstance(row[key], str) or len(row[key]) > MAX_TOKEN):
                    raise GateError('state_proof_limit')
                if row[key] is not None:
                    raw = db.execute('SELECT kind,identity,binding,token FROM messages WHERE digest=?',
                                     (sha(row[key].encode('ascii')),)).fetchone()
                    expected_kind = {'content': 'content_statement', 'status': 'status_snapshot', 'grant_proof': 'capability_grant'}[key]
                    if raw is None or tuple(raw) != (expected_kind, row['identity'], row['binding'], row[key]):
                        raise GateError('state_message_missing')
            status = limited_json(decode(row['status'].split('.')[1])) if row['status'] else None
            revoked = read_json(row['revoked'])
            if not isinstance(revoked, list) or revoked != sorted(set(revoked)):
                raise GateError('invalid_revocations')
            states.append({'identity': row['identity'], 'binding': binding,
                **{key: sha(row[key].encode('ascii')) if row[key] else None for key in ('content', 'status', 'grant_proof')},
                'epoch': status['body']['epoch'] if status else None,
                'sequence': status['body']['sequence'] if status else None, 'revoked': revoked})
        return sha(canonical({'store_id': self.store_id, 'context_sha256': self.context,
                              'state_revision': revision, 'states': states}))

    def _check_snapshot(self, db, control):
        if self._snapshot(db, control['revision']) != control['state_sha256']:
            raise GateError('state_digest_mismatch')

    def _pending(self, db):
        return db.execute('SELECT 1 FROM intents i LEFT JOIN receipts r USING(intent_id) WHERE r.intent_id IS NULL LIMIT 1').fetchone() is not None

    def _barrier(self, stage):
        """Fault hook, no-op outside bounded experiments."""

    def _normal(self, db, control):
        if self.storage_fault:
            raise GateError('storage_error')
        if control['mode'] != 'normal' or self._pending(db):
            raise GateError('recovery_required')

    def _base(self):
        return {'schema_version': 'cospace.test-recovery-journal/0.1', 'test_only': True,
                'store_id': self.store_id, 'context_sha256': self.context, 'generation': self.generation,
                'authorized': False, 'robot_ready': False}

    def _receipt(self, db, intent_id):
        row = db.execute('SELECT record FROM receipts WHERE intent_id=?', (intent_id,)).fetchone()
        return read_json(row[0]) if row else None

    def receipt(self, intent_id):
        self._uuid(intent_id)
        with self.lock.hold(self.timeout) as identity, self._db() as db:
            control = self._control(db, identity)
            self._check_snapshot(db, control)
            return self._receipt(db, intent_id)

    @staticmethod
    def _uuid(value):
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', value):
            raise GateError('invalid_intent_id')

    def accept(self, binding, token, kind, *, intent_id):
        self._uuid(intent_id)
        binding = read_json(canonical(binding))
        self._proof(token, kind, binding)
        digest, identity_key = sha(token.encode('ascii')), self._identity(binding)
        try:
            with self.lock.hold(self.timeout) as lock_identity:
                with self._db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    control = self._control(db, lock_identity)
                    self._check_snapshot(db, control)
                    old = db.execute('SELECT m.* FROM intents i JOIN messages m ON m.digest=i.message_sha256 WHERE intent_id=?', (intent_id,)).fetchone()
                    if old:
                        if tuple(old) != (digest, kind, identity_key, canonical(binding), token):
                            raise GateError('intent_conflict')
                        final = self._receipt(db, intent_id)
                        if final is not None:
                            return final
                        raise GateError('recovery_required')
                    self._normal(db, control)
                    message = db.execute('SELECT * FROM messages WHERE digest=?', (digest,)).fetchone()
                    if message and tuple(message) != (digest, kind, identity_key, canonical(binding), token):
                        raise GateError('message_conflict')
                    count, size = db.execute('SELECT count(*),coalesce(sum(length(CAST(token AS BLOB))),0) FROM messages').fetchone()
                    if (count + int(message is None) > self.limits.messages
                            or size + (len(token) if message is None else 0) > self.limits.token_bytes
                            or db.execute('SELECT count(*) FROM intents').fetchone()[0] >= self.limits.intents
                            or (db.execute('SELECT 1 FROM states WHERE identity=?', (identity_key,)).fetchone() is None
                                and db.execute('SELECT count(*) FROM states').fetchone()[0] >= self.limits.states)):
                        raise GateError('journal_quota')
                    if not message:
                        db.execute('INSERT INTO messages VALUES (?,?,?,?,?)', (digest, kind, identity_key, canonical(binding), token))
                    db.execute('INSERT INTO intents VALUES (?,?,?,?)', (intent_id, digest, self.generation, control['revision']))
                    self._barrier('before_prepare_commit')
                self._barrier('after_prepare_commit')
                with self._db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    control = self._control(db, lock_identity)
                    self._check_snapshot(db, control)
                    prepared = db.execute('SELECT prepared_revision,message_sha256 FROM intents WHERE intent_id=?', (intent_id,)).fetchone()
                    if (control['mode'] != 'normal' or prepared is None
                            or tuple(prepared) != (control['revision'], digest)):
                        raise GateError('prepared_context_changed')
                    before, revision = control['state_sha256'], control['revision']
                    proof = self._proof(token, kind, binding)
                    try:
                        changed = self._apply(db, binding, token, kind, proof)
                        outcome, reason = ('applied', 'state_applied') if changed else ('idempotent', 'same_state')
                    except GateError as error:
                        if error.code not in {'binding_conflict', 'epoch_not_authorized', 'state_rollback', 'state_conflict',
                            'revocation_terminal', 'status_missing', 'grant_status_mismatch', 'grant_predates_status', 'grant_requires_new_state'}:
                            raise
                        changed, outcome, reason = False, 'rejected', error.code
                    after_revision = revision + int(changed)
                    if after_revision > MAX_COUNTER:
                        raise GateError('revision_exhausted')
                    after = self._snapshot(db, after_revision)
                    self._barrier('after_state_write')
                    record = {**self._base(), 'record_kind': 'commit_receipt', 'intent_id': intent_id,
                        'token_sha256': digest, 'outcome': outcome, 'reason': reason, 'before_revision': revision,
                        'after_revision': after_revision, 'before_state_sha256': before, 'after_state_sha256': after}
                    db.execute('UPDATE control SET revision=?,state_sha256=? WHERE singleton=1', (after_revision, after))
                    db.execute('INSERT INTO receipts VALUES (?,?)', (intent_id, canonical(record)))
                    self._barrier('after_receipt_insert')
                self._barrier('after_apply_commit')
                return record
        except (sqlite3.Error, OSError, RuntimeError):
            self.storage_fault = True
            raise

    def _apply(self, db, binding, token, kind, proof):
        identity = self._identity(binding)
        row = db.execute('SELECT binding,content,status,grant_proof,revoked FROM states WHERE identity=?', (identity,)).fetchone()
        old = tuple(row) if row else (canonical(binding), None, None, None, canonical([]))
        if old[0] != canonical(binding):
            raise GateError('binding_conflict')
        content, status, grant, revoked = old[1], old[2], old[3], set(read_json(old[4]))
        document, body = proof['document'], proof['document']['body']
        if kind == 'content_statement':
            content = token
        elif kind == 'status_snapshot':
            if body['epoch'] != self.policy.epoch:
                raise GateError('epoch_not_authorized')
            previous = self._proof(status, kind, binding) if status else None
            if previous:
                if body['sequence'] < previous['document']['body']['sequence']:
                    raise GateError('state_rollback')
                if body['sequence'] == previous['document']['body']['sequence']:
                    if proof['payload_sha256'] != previous['payload_sha256']:
                        raise GateError('state_conflict')
                    return False
            if any(c['name'] in revoked and c['state'] != 'revoked' for c in body['capabilities']):
                raise GateError('revocation_terminal')
            revoked.update(c['name'] for c in body['capabilities'] if c['state'] == 'revoked')
            status, grant = token, None
        elif kind == 'capability_grant':
            if not status:
                raise GateError('status_missing')
            previous = self._proof(status, 'status_snapshot', binding)
            expected = {'epoch': previous['document']['body']['epoch'], 'sequence': previous['document']['body']['sequence'],
                        'payload_sha256': previous['payload_sha256']}
            if body['status'] != expected or body['policy_sha256'] != self.policy.digest():
                raise GateError('grant_status_mismatch')
            if document['issued_at'] < previous['document']['issued_at']:
                raise GateError('grant_predates_status')
            if grant:
                if self._proof(grant, kind, binding)['payload_sha256'] != proof['payload_sha256']:
                    raise GateError('grant_requires_new_state')
                return False
            grant = token
        new = (canonical(binding), content, status, grant, canonical(sorted(revoked)))
        if new == old and row:
            return False
        db.execute('INSERT INTO states VALUES (?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET binding=excluded.binding,content=excluded.content,status=excluded.status,grant_proof=excluded.grant_proof,revoked=excluded.revoked', (identity, *new))
        return True

    def decide(self, binding, capability, clock):
        try:
            with self.lock.hold(self.timeout) as identity, self._db() as db:
                db.execute('BEGIN')
                control = self._control(db, identity)
                self._normal(db, control)
                self._check_snapshot(db, control)
                return self._decide(binding, capability, clock)
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, IndexError) as error:
            if isinstance(error, (sqlite3.Error, OSError)):
                self.storage_fault = True
            return {'simulated_allowed': False, 'reason': getattr(error, 'code', 'storage_error'),
                    'authorized': False, 'robot_ready': False}

    def export_intent(self, intent_id):
        self._uuid(intent_id)
        with self.lock.hold(self.timeout) as identity, self._db() as db:
            self._control(db, identity)
            row = db.execute('SELECT i.*,m.* FROM intents i JOIN messages m ON m.digest=i.message_sha256 WHERE intent_id=?', (intent_id,)).fetchone()
            if row is None:
                raise GateError('intent_missing')
            return {**self._base(), 'record_kind': 'intent', 'intent_id': intent_id,
                    'generation': row['generation'], 'prepared_revision': row['prepared_revision'],
                    'message_kind': row['kind'], 'identity': row['identity'],
                    'binding_sha256': sha(row['binding']), 'token_sha256': row['digest'], 'token': row['token']}
