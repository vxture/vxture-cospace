"""J3 synthetic recovery with history replay, fenced plans and atomic completion."""
from contextlib import contextmanager
import sqlite3

from experiments.scripts.recovery_journal import JournalStore, MAX_COUNTER
from experiments.scripts.validity_probe import GateError
from packages.data.imports import canonical, sha
from packages.service.sample import read_json

REJECTIONS = {'binding_conflict', 'epoch_not_authorized', 'state_rollback', 'state_conflict',
              'revocation_terminal', 'status_missing', 'grant_status_mismatch',
              'grant_predates_status', 'grant_requires_new_state'}


class RecoveryStore(JournalStore):
    # Separate fresh experimental store, not a silent upgrade of the J2 database.
    STORE_VERSION = 3

    def _create_extra(self, db):
        db.execute('CREATE TABLE recovery_runs (recovery_id TEXT PRIMARY KEY, generation INTEGER NOT NULL, phase TEXT NOT NULL, result BLOB)')
        db.execute('CREATE UNIQUE INDEX one_active_recovery ON recovery_runs((1)) WHERE phase != \'reconciled\'')
        db.execute('CREATE TABLE recovery_plans (digest TEXT PRIMARY KEY, recovery_id TEXT NOT NULL REFERENCES recovery_runs(recovery_id), generation INTEGER NOT NULL, record BLOB NOT NULL)')
        for action in ('UPDATE', 'DELETE'):
            db.execute(f"CREATE TRIGGER immutable_plans_{action} BEFORE {action} ON recovery_plans BEGIN SELECT RAISE(ABORT,'immutable plan'); END")

    @contextmanager
    def _recovery_db(self):
        if self.storage_fault:
            raise GateError('storage_error')
        try:
            with self.lock.hold(self.timeout) as identity, self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                control = self._control(db, identity)
                self._check_snapshot(db, control)
                yield db, control
        except (sqlite3.Error, OSError, RuntimeError):
            self.storage_fault = True
            raise

    def _run(self, db, recovery_id):
        self._uuid(recovery_id)
        row = db.execute('SELECT * FROM recovery_runs WHERE recovery_id=?', (recovery_id,)).fetchone()
        if row is None:
            raise GateError('recovery_missing')
        return row

    def begin_recovery(self, recovery_id):
        self._uuid(recovery_id)
        with self._recovery_db() as (db, control):
            if control['mode'] != 'normal' or db.execute('SELECT 1 FROM recovery_runs WHERE recovery_id=?', (recovery_id,)).fetchone():
                raise GateError('recovery_already_started')
            if not self._pending(db):
                raise GateError('no_pending_intent')
            generation = control['generation'] + 1
            if generation > MAX_COUNTER:
                raise GateError('generation_exhausted')
            if db.execute('SELECT count(*) FROM recovery_runs').fetchone()[0] >= self.limits.intents:
                raise GateError('recovery_quota')
            db.execute('UPDATE control SET generation=?,mode=?', (generation, 'recovering'))
            db.execute('INSERT INTO recovery_runs VALUES (?,?,?,NULL)', (recovery_id, generation, 'blocked'))
            self._barrier('before_recovery_begin_commit')
        self._barrier('after_recovery_begin_commit')
        # Do not refresh this object: all pre-begin instances are fenced out.
        return {'recovery_id': recovery_id, 'generation': generation, 'phase': 'blocked',
                'authorized': False, 'robot_ready': False}

    def resume_recovery(self, recovery_id):
        with self._recovery_db() as (db, control):
            run = self._run(db, recovery_id)
            if control['mode'] != 'recovering' or run['phase'] == 'reconciled':
                raise GateError('recovery_not_active')
            generation = control['generation'] + 1
            if generation > MAX_COUNTER:
                raise GateError('generation_exhausted')
            db.execute('UPDATE control SET generation=?', (generation,))
            db.execute('UPDATE recovery_runs SET generation=?,phase=? WHERE recovery_id=?', (generation, 'blocked', recovery_id))
            self._barrier('before_recovery_resume_commit')
        self._barrier('after_recovery_resume_commit')
        return {'recovery_id': recovery_id, 'generation': generation, 'phase': 'blocked',
                'authorized': False, 'robot_ready': False}

    def _active(self, db, control, recovery_id):
        run = self._run(db, recovery_id)
        if (control['mode'] != 'recovering' or run['phase'] == 'reconciled'
                or run['generation'] != self.generation):
            raise GateError('recovery_not_active')
        return run

    def _unresolved(self, db):
        # LEFT JOIN makes missing messages visible rather than silently skipping them.
        rows = db.execute('SELECT i.*,m.kind,m.identity,m.binding,m.token FROM intents i LEFT JOIN messages m ON m.digest=i.message_sha256 LEFT JOIN receipts r ON r.intent_id=i.intent_id WHERE r.intent_id IS NULL ORDER BY i.intent_id LIMIT 201').fetchall()
        if not rows or len(rows) > 200:
            raise GateError('pending_set_invalid')
        return rows

    def _message(self, db, intent):
        self._uuid(intent['intent_id'])
        row = db.execute('SELECT * FROM messages WHERE digest=?', (intent['message_sha256'],)).fetchone()
        if row is None or sha(row['token'].encode('ascii')) != row['digest']:
            raise GateError('history_message_missing_or_changed')
        binding = read_json(row['binding'])
        if row['identity'] != self._identity(binding):
            raise GateError('history_identity_changed')
        proof = self._proof(row['token'], row['kind'], binding)
        return row, binding, proof

    def _evaluate(self, db, binding, token, kind, proof, *, recovery=False):
        try:
            changed = self._apply(db, binding, token, kind, proof)
            return ('applied', 'state_applied') if changed else ('idempotent', 'same_state')
        except GateError as error:
            if error.code not in REJECTIONS:
                raise
            # An unresolved revocation is never discarded as a logical rejection.
            if recovery and kind == 'status_snapshot' and any(c['state'] == 'revoked' for c in proof['document']['body']['capabilities']):
                raise GateError('unresolved_revocation_conflict') from error
            return 'rejected', error.code

    @contextmanager
    def _history(self, db, control):
        """Replay every committed receipt from empty state; compare current state hash."""
        scratch = sqlite3.connect(':memory:')
        scratch.row_factory = sqlite3.Row
        try:
            for table in ('messages', 'states'):
                sql = db.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?', ('table', table)).fetchone()[0]
                scratch.execute(sql)
            messages = db.execute('SELECT * FROM messages LIMIT ?', (self.limits.messages + 1,)).fetchall()
            intents = db.execute('SELECT * FROM intents LIMIT ?', (self.limits.intents + 1,)).fetchall()
            receipts = db.execute('SELECT r.*,i.message_sha256,i.generation AS prepared_generation,i.prepared_revision FROM receipts r LEFT JOIN intents i USING(intent_id) ORDER BY r.rowid LIMIT ?', (self.limits.intents + 1,)).fetchall()
            if len(messages) > self.limits.messages or len(intents) > self.limits.intents or len(receipts) > self.limits.intents:
                raise GateError('history_limit')
            if sum(len(m['token'].encode('ascii')) for m in messages) > self.limits.token_bytes:
                raise GateError('history_limit')
            for message in messages:
                scratch.execute('INSERT INTO messages VALUES (?,?,?,?,?)', tuple(message))
            revision = 0
            for item in receipts:
                if item['message_sha256'] is None:
                    raise GateError('history_intent_missing')
                record = read_json(item['record'])
                message, binding, proof = self._message(db, item)
                before = self._snapshot(scratch, revision)
                outcome, reason = self._evaluate(scratch, binding, message['token'], message['kind'], proof)
                next_revision = revision + int(outcome == 'applied')
                after = self._snapshot(scratch, next_revision)
                expected = {**self._base(), 'generation': record.get('generation'), 'record_kind': 'commit_receipt',
                    'intent_id': item['intent_id'], 'token_sha256': message['digest'], 'outcome': outcome,
                    'reason': reason, 'before_revision': revision, 'after_revision': next_revision,
                    'before_state_sha256': before, 'after_state_sha256': after}
                if (record != expected or type(record.get('generation')) is not int
                        or not item['prepared_generation'] <= record['generation'] <= self.generation
                        or not 0 <= item['prepared_revision'] <= revision):
                    raise GateError('history_receipt_mismatch')
                revision = next_revision
            if revision != control['revision'] or self._snapshot(scratch, revision) != control['state_sha256']:
                raise GateError('history_state_mismatch')
            yield scratch, revision
        finally:
            scratch.close()

    def _simulate(self, db, control, pending, *, write=False):
        items, receipts = [], []
        with self._history(db, control) as (scratch, revision):
            for intent in pending:
                message, binding, proof = self._message(db, intent)
                if not 0 <= intent['prepared_revision'] <= revision or not 1 <= intent['generation'] < self.generation:
                    raise GateError('prepared_history_mismatch')
                before = self._snapshot(scratch, revision)
                outcome, reason = self._evaluate(scratch, binding, message['token'], message['kind'], proof, recovery=True)
                after_revision = revision + int(outcome == 'applied')
                if after_revision > MAX_COUNTER:
                    raise GateError('revision_exhausted')
                after = self._snapshot(scratch, after_revision)
                items.append({'intent_id': intent['intent_id'], 'message_kind': message['kind'],
                    'identity': message['identity'], 'token_sha256': message['digest'],
                    'action': {'applied': 'apply', 'idempotent': 'record_idempotent', 'rejected': 'record_rejection'}[outcome], 'reason': reason})
                receipts.append({**self._base(), 'record_kind': 'commit_receipt', 'intent_id': intent['intent_id'],
                    'token_sha256': message['digest'], 'outcome': outcome, 'reason': reason,
                    'before_revision': revision, 'after_revision': after_revision,
                    'before_state_sha256': before, 'after_state_sha256': after})
                if write:
                    # Reapply to real state inside caller's single transaction.
                    result = self._evaluate(db, binding, message['token'], message['kind'], proof, recovery=True)
                    if result != (outcome, reason) or self._snapshot(db, after_revision) != after:
                        raise GateError('recovery_state_mismatch')
                    db.execute('INSERT INTO receipts VALUES (?,?)', (intent['intent_id'], canonical(receipts[-1])))
                    self._barrier('after_recovery_item')
                revision = after_revision
            target = self._snapshot(scratch, revision)
        return items, receipts, revision, target

    def _plan(self, db, control, recovery_id):
        pending = self._unresolved(db)
        items, _, revision, target = self._simulate(db, control, pending)
        references = [{k: i[k] for k in ('intent_id', 'message_kind', 'identity', 'token_sha256')} for i in items]
        return {**self._base(), 'record_kind': 'recovery_plan', 'recovery_id': recovery_id,
            'expected_state_revision': control['revision'], 'before_state_sha256': control['state_sha256'],
            'pending_set_sha256': sha(canonical(references)), 'target_state_sha256': target, 'items': items}

    def plan_recovery(self, recovery_id):
        with self._recovery_db() as (db, control):
            self._active(db, control, recovery_id)
            plan = self._plan(db, control, recovery_id)
            digest = sha(canonical(plan))
            if db.execute('SELECT count(*) FROM recovery_plans').fetchone()[0] >= self.limits.intents:
                if not db.execute('SELECT 1 FROM recovery_plans WHERE digest=?', (digest,)).fetchone():
                    raise GateError('recovery_quota')
            db.execute('INSERT OR IGNORE INTO recovery_plans VALUES (?,?,?,?)', (digest, recovery_id, self.generation, canonical(plan)))
            db.execute('UPDATE recovery_runs SET phase=? WHERE recovery_id=?', ('planned', recovery_id))
            self._barrier('before_recovery_plan_commit')
        self._barrier('after_recovery_plan_commit')
        return plan

    def commit_recovery(self, plan):
        # Snapshot caller input before acquiring the lock.
        plan = read_json(canonical(plan))
        if not isinstance(plan, dict) or not isinstance(plan.get('recovery_id'), str):
            raise GateError('invalid_plan')
        digest = sha(canonical(plan))
        with self._recovery_db() as (db, control):
            run = self._active(db, control, plan['recovery_id'])
            saved = db.execute('SELECT record FROM recovery_plans WHERE digest=? AND recovery_id=? AND generation=?',
                               (digest, plan['recovery_id'], self.generation)).fetchone()
            if run['phase'] != 'planned' or saved is None or saved[0] != canonical(plan):
                raise GateError('plan_not_current')
            current = self._plan(db, control, plan['recovery_id'])
            if current != plan:
                raise GateError('plan_compare_failed')
            if self.generation == MAX_COUNTER:
                raise GateError('generation_exhausted')
            _, _, revision, target = self._simulate(db, control, self._unresolved(db), write=True)
            if target != plan['target_state_sha256'] or self._pending(db):
                raise GateError('recovery_incomplete')
            result = {**self._base(), 'record_kind': 'recovery_result', 'recovery_id': plan['recovery_id'],
                'plan_sha256': digest, 'phase': 'reconciled', 'state_revision': revision,
                'state_sha256': target, 'reason': 'history_reconciled'}
            db.execute('UPDATE control SET revision=?,state_sha256=?,mode=?,generation=generation+1', (revision, target, 'normal'))
            db.execute('UPDATE recovery_runs SET phase=?,result=? WHERE recovery_id=?', ('reconciled', canonical(result), plan['recovery_id']))
            self._barrier('before_recovery_finish_commit')
        self._barrier('after_recovery_finish_commit')
        # Completed owner is also fenced until a new object is opened.
        self.storage_fault = True
        return result

    def recovery_result(self, recovery_id):
        # Diagnostic read remains possible after lost response/storage fault.
        with self.lock.hold(self.timeout) as identity, self._db() as db:
            self._control(db, identity)
            run = self._run(db, recovery_id)
            return read_json(run['result']) if run['result'] else {**self._base(),
                'record_kind': 'recovery_result', 'recovery_id': recovery_id, 'plan_sha256': None,
                'phase': 'blocked', 'state_revision': db.execute('SELECT revision FROM control').fetchone()[0],
                'state_sha256': db.execute('SELECT state_sha256 FROM control').fetchone()[0], 'reason': 'recovery_not_finished'}
