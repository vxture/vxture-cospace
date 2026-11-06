"""J2 atomic journal, real process interruption and existing proof/time semantics."""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

import pytest

from experiments.scripts.recovery_journal import JournalStore, JournalLimits
from experiments.scripts.validity_probe import GateError
from packages.data.imports import canonical, sha
from packages.data.structure import LiteralIntegerValidator
from tests.test_validity_probe import gate, proofs, CAP
from tests.test_trust_proof import token

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='J2 uses Windows LockFileEx prototype')


@contextmanager
def connection(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


@pytest.fixture
def journal(gate, tmp_path):
    value = JournalStore.bootstrap(tmp_path / 'journal', gate['context'][2], gate['policy'])
    for kind, proof in [('content_statement', token(gate['context'][0], gate['content'])),
                        ('status_snapshot', proofs(gate)[0]), ('capability_grant', proofs(gate)[1])]:
        value.accept(gate['binding'], proof, kind, intent_id=str(uuid.uuid4()))
    gate['journal'] = value
    return gate


def accept(journal, proof, kind='status_snapshot', intent_id=None):
    return journal['journal'].accept(journal['binding'], proof, kind, intent_id=intent_id or str(uuid.uuid4()))


def decide(journal, store=None):
    return (store or journal['journal']).decide(journal['binding'], CAP, journal['clock'])


def reopen(journal):
    old = journal['journal']
    return JournalStore(old.root, journal['context'][2], journal['policy'], limits=old.limits)


def counts(store):
    with connection(store.path) as db:
        return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                     for table in ('messages', 'intents', 'receipts', 'states'))


def test_original_bytes_receipts_schema_and_fixed_deadline(journal):
    store = journal['journal']
    assert decide(journal)['deadline'] == 130
    validator = LiteralIntegerValidator(json.loads(Path('contracts/schemas/recovery-journal-v0.1.schema.json').read_text()))
    with connection(store.path) as db:
        ids = [r[0] for r in db.execute('SELECT intent_id FROM intents')]
    for intent_id in ids:
        record = store.export_intent(intent_id)
        validator.validate(record)
        validator.validate(store.receipt(intent_id))
        assert sha(record['token'].encode('ascii')) == record['token_sha256']
    result = decide(journal)
    assert result['simulated_allowed'] and not result['authorized'] and not result['robot_ready']


def test_same_id_reads_receipt_different_bytes_rejected_and_duplicates_do_not_extend(journal):
    status, _ = proofs(journal)
    intent = str(uuid.uuid4())
    first = accept(journal, status, intent_id=intent)
    assert first['outcome'] == 'idempotent'
    assert first['before_revision'] == first['after_revision']
    before = counts(journal['journal'])
    assert accept(journal, status, intent_id=intent) == first
    assert counts(journal['journal']) == before
    other = proofs(journal, sequence=2)[0]
    with pytest.raises(GateError, match='intent_conflict'):
        accept(journal, other, intent_id=intent)
    journal['tick'][1] += 20
    assert decide(journal)['reason'] == 'expired'


def test_rejection_is_receipted_without_state_change(journal):
    first = accept(journal, proofs(journal, sequence=2)[0])
    rejected = accept(journal, proofs(journal)[0])
    assert rejected['outcome'] == 'rejected' and rejected['reason'] == 'state_rollback'
    assert rejected['before_revision'] == rejected['after_revision'] == first['after_revision']
    assert rejected['before_state_sha256'] == rejected['after_state_sha256']
    assert decide(journal)['reason'] == 'grant_missing'


def test_terminal_revocation_and_old_grant_stay_rejected(journal):
    revoked, _ = proofs(journal, sequence=2, state='revoked')
    assert accept(journal, revoked)['outcome'] == 'applied'
    newer, _ = proofs(journal, sequence=3)
    assert accept(journal, newer)['reason'] == 'revocation_terminal'
    assert accept(journal, proofs(journal)[1], 'capability_grant')['reason'] == 'grant_status_mismatch'
    assert decide(journal, reopen(journal))['reason'] == 'revoked'


@pytest.mark.parametrize('stage,pending', [('before_prepare_commit', False),
    ('after_prepare_commit', True), ('after_state_write', True), ('after_receipt_insert', True)])
def test_fault_boundaries_never_commit_half_state_receipt(journal, stage, pending):
    store = journal['journal']
    intent = str(uuid.uuid4())
    before = counts(store)
    def barrier(current):
        if current == stage:
            raise sqlite3.OperationalError('injected')
    store._barrier = barrier
    with pytest.raises(sqlite3.OperationalError):
        accept(journal, proofs(journal, sequence=2, state='revoked')[0], intent_id=intent)
    new = reopen(journal)
    after = counts(new)
    assert after[2:] == before[2:]
    assert new.receipt(intent) is None
    assert decide(journal, new)['reason'] == ('recovery_required' if pending else 'synthetic_conditions_met')
    assert decide(journal)['reason'] == 'storage_error'
    if pending:
        assert new.export_intent(intent)['token']
        with pytest.raises(GateError, match='recovery_required'):
            new.accept(journal['binding'], proofs(journal, sequence=3)[0], 'status_snapshot', intent_id=str(uuid.uuid4()))


def test_response_lost_returns_existing_receipt_without_reapply(journal):
    store = journal['journal']
    intent = str(uuid.uuid4())
    proof = proofs(journal, sequence=2, state='revoked')[0]
    def fail(stage):
        if stage == 'after_apply_commit':
            raise OSError('response lost')
    store._barrier = fail
    with pytest.raises(OSError):
        accept(journal, proof, intent_id=intent)
    new = reopen(journal)
    before = counts(new)
    receipt = new.receipt(intent)
    assert receipt['outcome'] == 'applied'
    assert new.accept(journal['binding'], proof, 'status_snapshot', intent_id=intent) == receipt
    assert counts(new) == before and decide(journal, new)['reason'] == 'revoked'


def test_immutable_history_survives_latest_status_replacement(journal):
    store = journal['journal']
    old = proofs(journal, sequence=2)[0]
    intent = str(uuid.uuid4())
    first = accept(journal, old, intent_id=intent)
    accept(journal, proofs(journal, sequence=3)[0])
    assert store.export_intent(intent)['token'] == old
    assert store.receipt(intent) == first
    with connection(store.path) as db:
        for table in ('messages', 'intents', 'receipts'):
            with pytest.raises(sqlite3.IntegrityError, match='immutable'):
                db.execute(f'DELETE FROM {table}')


def test_receipt_constraint_failure_rolls_back_state_and_control(journal):
    store = journal['journal']
    with connection(store.path) as db:
        before = db.execute('SELECT revision,state_sha256 FROM control').fetchone()
        db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT,'injected constraint'); END")
    intent = str(uuid.uuid4())
    with pytest.raises(sqlite3.IntegrityError):
        accept(journal, proofs(journal, sequence=2, state='revoked')[0], intent_id=intent)
    with connection(store.path) as db:
        assert db.execute('SELECT revision,state_sha256 FROM control').fetchone() == before
        assert db.execute('SELECT count(*) FROM receipts WHERE intent_id=?', (intent,)).fetchone()[0] == 0
    assert decide(journal, reopen(journal))['reason'] == 'recovery_required'


def test_invalid_signature_creates_no_intent(journal):
    before = counts(journal['journal'])
    with pytest.raises(GateError, match='invalid_proof'):
        accept(journal, 'invalid.jws.value')
    assert counts(journal['journal']) == before and decide(journal)['simulated_allowed']


def test_delegated_deadline_used_in_journal(gate, tmp_path):
    from tests.test_validity_hardening import delegated
    trust, _, _ = delegated(gate, tmp_path)
    store = JournalStore.bootstrap(tmp_path / 'delegated-journal', trust, gate['policy'])
    gate['journal'] = store
    accept(gate, token(gate['context'][0], gate['content']), 'content_statement')
    status, grant = proofs(gate)
    accept(gate, status)
    accept(gate, grant, 'capability_grant')
    assert decide(gate)['deadline'] == 125
    gate['tick'][1] += 15
    assert decide(gate)['reason'] == 'expired'


def test_state_quota_preserves_existing_history(journal, tmp_path):
    import copy
    store = JournalStore.bootstrap(tmp_path / 'state-limited', journal['context'][2], journal['policy'], limits=JournalLimits(states=1))
    content = token(journal['context'][0], journal['content'])
    store.accept(journal['binding'], content, 'content_statement', intent_id=str(uuid.uuid4()))
    other = copy.deepcopy(journal['content'])
    other['binding']['package_sha256'] = 'f' * 64
    signed = token(journal['context'][0], other)
    before = counts(store)
    with pytest.raises(GateError, match='journal_quota'):
        store.accept(other['binding'], signed, 'content_statement', intent_id=str(uuid.uuid4()))
    assert counts(store) == before


def test_serialized_competing_states_have_receipted_single_winner(journal):
    from concurrent.futures import ThreadPoolExecutor
    stores = [reopen(journal), reopen(journal)]
    messages = [proofs(journal, sequence=2)[0], proofs(journal, sequence=2, state='restricted')[0]]
    with ThreadPoolExecutor(2) as pool:
        tasks = [pool.submit(s.accept, journal['binding'], message, 'status_snapshot', intent_id=str(uuid.uuid4()))
                 for s, message in zip(stores, messages)]
        results = [task.result(timeout=15) for task in tasks]
    assert sorted(r['outcome'] for r in results) == ['applied', 'rejected']
    assert next(r for r in results if r['outcome'] == 'rejected')['reason'] == 'state_conflict'


@pytest.mark.parametrize('limits', [JournalLimits(messages=1), JournalLimits(intents=1), JournalLimits(token_bytes=1)])
def test_quotas_reject_without_dropping_history_or_preparing(journal, tmp_path, limits):
    new = JournalStore.bootstrap(tmp_path / str(uuid.uuid4()), journal['context'][2], journal['policy'], limits=limits)
    binding = journal['binding']
    content = token(journal['context'][0], journal['content'])
    if limits.token_bytes == 1:
        with pytest.raises(GateError, match='journal_quota'):
            new.accept(binding, content, 'content_statement', intent_id=str(uuid.uuid4()))
        assert counts(new) == (0, 0, 0, 0)
    else:
        new.accept(binding, content, 'content_statement', intent_id=str(uuid.uuid4()))
        before = counts(new)
        with pytest.raises(GateError, match='journal_quota'):
            new.accept(binding, proofs(journal)[0], 'status_snapshot', intent_id=str(uuid.uuid4()))
        assert counts(new) == before


def test_corruption_config_and_missing_database_refuse_recreate(journal):
    store = journal['journal']
    with pytest.raises(GateError, match='context'):
        JournalStore(store.root, journal['context'][2], journal['policy'], limits=JournalLimits(intents=10))
    with connection(store.path) as db:
        db.execute('UPDATE states SET content=NULL')
    assert decide(journal)['reason'] == 'state_digest_mismatch'
    store.path.unlink()
    assert not decide(journal)['simulated_allowed'] and not store.path.exists()


@pytest.mark.parametrize('stage,committed', [('before_prepare_commit', False), ('after_prepare_commit', False), ('after_state_write', False),
    ('after_receipt_insert', False), ('after_apply_commit', True)])
def test_real_process_exit_around_transaction_boundaries(journal, tmp_path, stage, committed):
    store = journal['journal']
    intent = str(uuid.uuid4())
    proof = proofs(journal, sequence=2, state='revoked')[0]
    request = {'trust': journal['context'][1], 'policy': vars(journal['policy']), 'binding': journal['binding'],
               'token': proof, 'intent': intent, 'stage': stage, 'root': str(store.root)}
    request_path = tmp_path / 'request.json'
    request_path.write_bytes(canonical(request))
    code = '''
import json,sys,os
from pathlib import Path
from experiments.scripts.trust_proof import load_test_trust
from experiments.scripts.validity_probe import Policy
from experiments.scripts.recovery_journal import JournalStore
d=json.loads(Path(sys.argv[1]).read_bytes())
s=JournalStore(d['root'],load_test_trust(json.dumps(d['trust']).encode()),Policy(**d['policy']))
s._barrier=lambda stage:os._exit(76) if stage==d['stage'] else None
s.accept(d['binding'],d['token'],'status_snapshot',intent_id=d['intent'])
'''
    result = subprocess.run([sys.executable, '-c', code, str(request_path)], timeout=20, capture_output=True)
    assert result.returncode == 76, result.stderr
    new = reopen(journal)
    receipt = new.receipt(intent)
    assert bool(receipt) == committed
    if stage == 'before_prepare_commit':
        assert decide(journal, new)['simulated_allowed']
        with pytest.raises(GateError, match='intent_missing'):
            new.export_intent(intent)
    else:
        assert decide(journal, new)['reason'] == ('revoked' if committed else 'recovery_required')
        assert new.export_intent(intent)['token'] == proof
