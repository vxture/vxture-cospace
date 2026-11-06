"""J3 recovery fences, full history replay and atomic completion with fault barriers."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

import pytest

from experiments.scripts.recovery_state import RecoveryStore
from experiments.scripts.recovery_journal import JournalStore
from experiments.scripts.validity_probe import GateError
from packages.data.imports import canonical, sha
from packages.data.structure import LiteralIntegerValidator
from tests.test_validity_probe import gate, proofs, CAP
from tests.test_trust_proof import token
from tests.test_recovery_journal import connection, accept, decide, counts

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows lock required')


@pytest.fixture
def recovery(gate, tmp_path):
    store = RecoveryStore.bootstrap(tmp_path / 'recovery', gate['context'][2], gate['policy'])
    for kind, proof in [('content_statement', token(gate['context'][0], gate['content'])),
                        ('status_snapshot', proofs(gate)[0]), ('capability_grant', proofs(gate)[1])]:
        store.accept(gate['binding'], proof, kind, intent_id=str(uuid.uuid4()))
    gate['journal'] = store
    return gate


def reopen(fixture):
    store = fixture['journal']
    return RecoveryStore(store.root, fixture['context'][2], fixture['policy'])


def pending(fixture, signed=None, kind='status_snapshot'):
    store = fixture['journal']
    intent = str(uuid.uuid4())
    def fail(stage):
        if stage == 'after_prepare_commit':
            raise sqlite3.OperationalError('prepare interrupted')
    store._barrier = fail
    with pytest.raises(sqlite3.OperationalError):
        accept(fixture, signed or proofs(fixture, sequence=2, state='revoked')[0], kind, intent)
    fixture['journal'] = reopen(fixture)
    return intent


def plan(fixture):
    recovery_id = str(uuid.uuid4())
    fixture['journal'].begin_recovery(recovery_id)
    fixture['journal'] = reopen(fixture)
    return recovery_id, fixture['journal'].plan_recovery(recovery_id)


def test_recover_revocation_with_schema_and_fenced_completion(recovery):
    intent = pending(recovery)
    before = recovery['journal']
    rid, proposed = plan(recovery)
    validator = LiteralIntegerValidator(json.loads(Path('contracts/schemas/recovery-journal-v0.1.schema.json').read_text()))
    validator.validate(proposed)
    assert proposed['items'][0]['action'] == 'apply'
    assert decide(recovery, before)['reason'] == 'stale_generation'
    owner = recovery['journal']
    observer = reopen(recovery)
    result = owner.commit_recovery(proposed)
    validator.validate(result)
    for old in (before, owner, observer):
        assert decide(recovery, old)['reason'] == 'stale_generation'
    new = reopen(recovery)
    assert new.recovery_result(rid) == result
    assert new.receipt(intent)['generation'] == proposed['generation']
    assert decide(recovery, new)['reason'] == 'revoked'
    with pytest.raises(GateError, match='recovery_not_active'):
        new.resume_recovery(rid)


def test_resume_invalidates_old_object_and_old_plan(recovery):
    pending(recovery)
    rid, old = plan(recovery)
    original = recovery['journal']
    original.resume_recovery(rid)
    assert decide(recovery, original)['reason'] == 'stale_generation'
    new = reopen(recovery)
    with pytest.raises(GateError, match='plan_not_current'):
        new.commit_recovery(old)
    proposed = new.plan_recovery(rid)
    assert proposed['generation'] == old['generation'] + 1
    new.commit_recovery(proposed)
    assert decide(recovery, reopen(recovery))['reason'] == 'revoked'


@pytest.mark.parametrize('field,value', [('store_id', '00000000-0000-0000-0000-000000000000'),
    ('context_sha256', '0' * 64), ('generation', 99), ('expected_state_revision', 99),
    ('before_state_sha256', '0' * 64), ('pending_set_sha256', '0' * 64),
    ('target_state_sha256', '0' * 64), ('items', []), ('authorized', True)])
def test_changed_plan_fields_cannot_be_committed(recovery, field, value):
    pending(recovery)
    rid, proposed = plan(recovery)
    changed = copy.deepcopy(proposed)
    changed[field] = value
    before = counts(recovery['journal'])
    with pytest.raises(GateError, match='plan_not_current'):
        recovery['journal'].commit_recovery(changed)
    assert counts(recovery['journal']) == before
    assert recovery['journal'].recovery_result(rid)['phase'] == 'blocked'


@pytest.mark.parametrize('stage', ['after_recovery_item', 'before_recovery_finish_commit'])
def test_completion_fault_rolls_back_state_receipt_and_mode(recovery, stage):
    intent = pending(recovery)
    rid, proposed = plan(recovery)
    store = recovery['journal']
    before = counts(store)
    def fail(current):
        if current == stage:
            raise sqlite3.OperationalError('recovery fault')
    store._barrier = fail
    with pytest.raises(sqlite3.OperationalError):
        store.commit_recovery(proposed)
    new = reopen(recovery)
    assert counts(new) == before and new.receipt(intent) is None
    assert new.recovery_result(rid)['phase'] == 'blocked'
    assert decide(recovery, new)['reason'] == 'recovery_required'


def test_completed_response_loss_read_result_without_reapply(recovery):
    pending(recovery)
    rid, proposed = plan(recovery)
    def fail(stage):
        if stage == 'after_recovery_finish_commit':
            raise OSError('lost result')
    recovery['journal']._barrier = fail
    with pytest.raises(OSError):
        recovery['journal'].commit_recovery(proposed)
    new = reopen(recovery)
    assert new.recovery_result(rid)['phase'] == 'reconciled'
    before = counts(new)
    with pytest.raises(GateError, match='recovery_not_active'):
        new.commit_recovery(proposed)
    assert counts(new) == before


@pytest.mark.parametrize('damage', ['missing_message', 'bad_signature', 'missing_receipt'])
def test_unverifiable_history_never_cleared(recovery, damage):
    intent = pending(recovery)
    rid, _ = plan(recovery)
    store = recovery['journal']
    with connection(store.path) as db:
        if damage == 'missing_message':
            db.execute('DROP TRIGGER immutable_messages_DELETE')
            digest = db.execute('SELECT message_sha256 FROM intents WHERE intent_id=?', (intent,)).fetchone()[0]
            db.execute('DELETE FROM messages WHERE digest=?', (digest,))
        elif damage == 'bad_signature':
            db.execute('DROP TRIGGER immutable_messages_UPDATE')
            db.execute('DROP TRIGGER immutable_intents_UPDATE')
            digest = db.execute('SELECT message_sha256 FROM intents WHERE intent_id=?', (intent,)).fetchone()[0]
            original = db.execute('SELECT token FROM messages WHERE digest=?', (digest,)).fetchone()[0]
            header, payload, signature = original.split('.')
            changed = '.'.join((header, payload, ('A' if signature[0] != 'A' else 'B') + signature[1:]))
            changed_digest = sha(changed.encode('ascii'))
            db.execute('UPDATE messages SET digest=?,token=? WHERE digest=?', (changed_digest, changed, digest))
            db.execute('UPDATE intents SET message_sha256=? WHERE intent_id=?', (changed_digest, intent))
        else:
            db.execute('DROP TRIGGER immutable_receipts_DELETE')
            db.execute('DELETE FROM receipts WHERE rowid=(SELECT min(rowid) FROM receipts)')
    with pytest.raises((GateError, ValueError)):
        store.plan_recovery(rid)
    assert store.recovery_result(rid)['phase'] == 'blocked'
    assert decide(recovery, store)['reason'] == 'recovery_required'


def test_expired_idempotent_recovery_does_not_renew(recovery):
    pending(recovery, proofs(recovery)[0])
    recovery['tick'][1] += 30
    rid, proposed = plan(recovery)
    assert proposed['items'][0]['action'] == 'record_idempotent'
    recovery['journal'].commit_recovery(proposed)
    assert decide(recovery, reopen(recovery))['reason'] == 'expired'


def test_second_recovery_replays_previous_recovery_receipts(recovery):
    pending(recovery, proofs(recovery)[0])
    _, first = plan(recovery)
    recovery['journal'].commit_recovery(first)
    recovery['journal'] = reopen(recovery)
    pending(recovery, proofs(recovery)[0])
    _, second = plan(recovery)
    assert second['generation'] > first['generation']
    recovery['journal'].commit_recovery(second)
    assert decide(recovery, reopen(recovery))['simulated_allowed']


def test_terminal_revocation_cannot_be_undone_by_recovery(recovery):
    accept(recovery, proofs(recovery, sequence=2, state='revoked')[0])
    intent = pending(recovery, proofs(recovery, sequence=3)[0])
    _, proposed = plan(recovery)
    assert proposed['items'][0]['action'] == 'record_rejection'
    assert proposed['items'][0]['reason'] == 'revocation_terminal'
    recovery['journal'].commit_recovery(proposed)
    fresh = reopen(recovery)
    assert fresh.receipt(intent)['outcome'] == 'rejected'
    assert decide(recovery, fresh)['reason'] == 'revoked'


def test_j2_existing_store_is_not_upgraded(gate, tmp_path):
    old = JournalStore.bootstrap(tmp_path / 'j2-only', gate['context'][2], gate['policy'])
    with pytest.raises(GateError, match='unsupported_journal'):
        RecoveryStore(old.root, gate['context'][2], gate['policy'])
    with connection(old.path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2


def test_no_implicit_begin_or_replacing_active_recovery(recovery):
    with pytest.raises(GateError, match='no_pending_intent'):
        recovery['journal'].begin_recovery(str(uuid.uuid4()))
    pending(recovery)
    rid, _ = plan(recovery)
    with pytest.raises(GateError, match='recovery_already_started'):
        recovery['journal'].begin_recovery(str(uuid.uuid4()))
    with pytest.raises(GateError, match='recovery_missing'):
        recovery['journal'].resume_recovery(str(uuid.uuid4()))
    assert recovery['journal'].recovery_result(rid)['phase'] == 'blocked'


def test_changed_actual_pending_set_rejects_sealed_plan(recovery):
    intent = pending(recovery)
    rid, proposed = plan(recovery)
    store = recovery['journal']
    with connection(store.path) as db:
        db.execute('INSERT INTO intents SELECT ?,message_sha256,generation,prepared_revision FROM intents WHERE intent_id=?',
                   (str(uuid.uuid4()), intent))
    with pytest.raises(GateError, match='plan_compare_failed'):
        store.commit_recovery(proposed)
    assert store.recovery_result(rid)['phase'] == 'blocked'


def test_seeded_multiple_pending_items_fail_atomically(recovery):
    # Normal J2 permits only one pending; seed another for batch rollback coverage.
    intent = pending(recovery)
    store = recovery['journal']
    with connection(store.path) as db:
        db.execute('INSERT INTO intents SELECT ?,message_sha256,generation,prepared_revision FROM intents WHERE intent_id=?',
                   (str(uuid.uuid4()), intent))
    rid, proposed = plan(recovery)
    assert len(proposed['items']) == 2
    before = counts(recovery['journal'])
    seen = []
    def fail(stage):
        if stage == 'after_recovery_item':
            seen.append(stage)
            if len(seen) == 2:
                raise sqlite3.OperationalError('second item failed')
    recovery['journal']._barrier = fail
    with pytest.raises(sqlite3.OperationalError):
        recovery['journal'].commit_recovery(proposed)
    new = reopen(recovery)
    assert counts(new) == before and new.recovery_result(rid)['phase'] == 'blocked'


def test_unresolved_conflicting_revocation_stays_blocked(recovery):
    pending(recovery, proofs(recovery, sequence=1, state='revoked')[0])
    rid = str(uuid.uuid4())
    recovery['journal'].begin_recovery(rid)
    new = reopen(recovery)
    with pytest.raises(GateError, match='unresolved_revocation_conflict'):
        new.plan_recovery(rid)
    assert new.recovery_result(rid)['phase'] == 'blocked'


@pytest.mark.parametrize('stage', ['after_recovery_begin_commit', 'after_recovery_plan_commit',
    'after_recovery_item', 'before_recovery_finish_commit', 'after_recovery_finish_commit'])
def test_process_exit_keeps_recovery_control_and_atomic_result(recovery, tmp_path, stage):
    intent = pending(recovery)
    rid = str(uuid.uuid4())
    store = recovery['journal']
    request = {'root': str(store.root), 'trust': recovery['context'][1], 'policy': vars(recovery['policy']),
               'rid': rid, 'stage': stage}
    path = tmp_path / 'recovery-request.json'
    path.write_bytes(canonical(request))
    code = '''
import sys,os,json
from pathlib import Path
from experiments.scripts.trust_proof import load_test_trust
from experiments.scripts.validity_probe import Policy
from experiments.scripts.recovery_state import RecoveryStore
d=json.loads(Path(sys.argv[1]).read_bytes())
def opened():return RecoveryStore(d['root'],load_test_trust(json.dumps(d['trust']).encode()),Policy(**d['policy']))
def hook(s):s._barrier=lambda stage:os._exit(77) if stage==d['stage'] else None;return s
hook(opened()).begin_recovery(d['rid'])
s=hook(opened());p=s.plan_recovery(d['rid']);s.commit_recovery(p)
'''
    result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, timeout=25)
    assert result.returncode == 77, result.stderr
    new = reopen(recovery)
    committed = stage == 'after_recovery_finish_commit'
    assert (new.recovery_result(rid)['phase'] == 'reconciled') == committed
    assert bool(new.receipt(intent)) == committed
    assert decide(recovery, new)['reason'] == ('revoked' if committed else 'recovery_required')
