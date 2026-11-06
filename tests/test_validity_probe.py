"""R2b synthetic gate: persistent order, terminal revocation and time bounds."""
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from experiments.scripts.validity_probe import ValidityStore, IntervalClock, Policy, GateError, GuardedSession
from experiments.scripts.trust_proof import verify
from packages.data.imports import canonical, sha
from packages.infrastructure.agent_files import FilePackages
from tests.test_trust_proof import setup as proof_setup, token

CAP = 'synthetic_point_query'


@pytest.fixture
def gate(tmp_path):
    context = proof_setup.__wrapped__()
    seed, trust_doc, trust, content = context
    policy = Policy('test-device', 'test-deployment', 30, 0, 180)
    store = ValidityStore(tmp_path / 'ledger', trust, policy, bootstrap=True)
    binding = content['binding']
    store.accept(binding, token(seed, content), 'content_statement')
    tick = ['boot-a', 10.0]
    clock = IntervalClock(lambda: tuple(tick), ('boot-a', 10.0, 110, 110))
    value = {'context': context, 'store': store, 'policy': policy, 'binding': binding, 'tick': tick,
             'clock': clock, 'tmp': tmp_path, 'content': content}
    status, grant = proofs(value)
    store.accept(binding, status, 'status_snapshot')
    store.accept(binding, grant, 'capability_grant')
    return value


def proofs(gate, sequence=1, state='allowed', issued=100, change=None):
    seed, _, _, original = gate['context']
    status = copy.deepcopy(original)
    status.update(kind='status_snapshot', issued_at=issued)
    status['body'] = {'epoch': 1, 'sequence': sequence, 'audience': 'test-device', 'expires_at': 200,
                      'capabilities': [{'name': CAP, 'state': state, 'reason': 'synthetic test'}]}
    if change:
        change(status)
    payload_digest = sha(canonical(status))
    grant = copy.deepcopy(original)
    grant.update(kind='capability_grant', issued_at=issued)
    grant['body'] = {'audience': 'test-device', 'capabilities': [CAP], 'policy_sha256': gate['policy'].digest(),
                     'status': {'epoch': status['body']['epoch'], 'sequence': sequence, 'payload_sha256': payload_digest},
                     'not_before': issued, 'expires_at': 200, 'max_offline_seconds': 60}
    return token(seed, status, 'test-validity'), token(seed, grant, 'test-validity')


def decision(gate, clock=None):
    return gate['store'].decide(gate['binding'], CAP, clock or gate['clock'])


def test_normal_and_duplicate_does_not_extend_offline_budget(gate):
    first = decision(gate)
    assert first['simulated_allowed'] and not first['authorized'] and not first['robot_ready']
    assert first['deadline'] == 130
    status, grant = proofs(gate)
    gate['tick'][1] += 20
    gate['store'].accept(gate['binding'], status, 'status_snapshot')
    gate['store'].accept(gate['binding'], grant, 'capability_grant')
    assert decision(gate)['reason'] == 'expired'


@pytest.mark.parametrize('earliest,latest,reason', [(99,99,'not_yet_valid'), (99,100,'validity_unknown'),
    (100,100,'synthetic_conditions_met'), (129,129,'synthetic_conditions_met'),
    (129,130,'validity_unknown'), (130,130,'expired')])
def test_time_interval_boundaries(gate, earliest, latest, reason):
    clock = IntervalClock(lambda: ('b', 0), ('b', 0, earliest, latest))
    assert decision(gate, clock)['reason'] == reason


def test_boot_change_counter_rollback_and_no_anchor_fail_closed(gate):
    assert decision(gate)['simulated_allowed']
    gate['tick'][0] = 'boot-b'
    assert decision(gate)['reason'] == 'validity_unknown'
    gate['tick'][0] = 'boot-a'
    assert decision(gate)['reason'] == 'validity_unknown'  # Sticky invalidation.
    clock = IntervalClock(lambda: tuple(gate['tick']), ('boot-a', 10, 110, 110))
    gate['tick'][1] = 9
    assert decision(gate, clock)['reason'] == 'validity_unknown'
    assert decision(gate, IntervalClock(lambda: ('boot-a', 10)))['reason'] == 'validity_unknown'


def test_rollback_conflict_and_epoch_rejected(gate):
    store, binding = gate['store'], gate['binding']
    status, _ = proofs(gate, sequence=2)
    store.accept(binding, status, 'status_snapshot')
    assert decision(gate)['reason'] == 'grant_missing'
    for rejected, code in [
        (proofs(gate)[0], 'state_rollback'),
        (proofs(gate, sequence=2, state='restricted')[0], 'state_conflict'),
        (proofs(gate, sequence=3, change=lambda d: d['body'].update(epoch=2))[0], 'epoch_not_authorized')]:
        with pytest.raises(GateError) as error:
            store.accept(binding, rejected, 'status_snapshot')
        assert error.value.code == code


def test_terminal_revocation_survives_restart_and_omission(gate):
    store, binding = gate['store'], gate['binding']
    revoked, _ = proofs(gate, sequence=2, state='revoked')
    store.accept(binding, revoked, 'status_snapshot')
    gate['store'] = ValidityStore(store.root, gate['context'][2], gate['policy'])
    assert decision(gate)['reason'] == 'revoked'
    newer, _ = proofs(gate, sequence=3)
    with pytest.raises(GateError, match='terminal'):
        gate['store'].accept(binding, newer, 'status_snapshot')
    omitted, _ = proofs(gate, sequence=3, change=lambda d: d['body']['capabilities'][0].update(name='other'))
    gate['store'].accept(binding, omitted, 'status_snapshot')
    assert decision(gate)['reason'] == 'revoked'


def test_grant_relation_policy_and_reissue_require_new_state(gate):
    seed, _, _, original = gate['context']
    _, grant = proofs(gate)
    body = verify(grant, gate['context'][2], expected_kind='capability_grant', expected_deployment='test-deployment',
                  expected_binding=gate['binding'], expected_audience='test-device')['document']
    for change, code in [(lambda d: d['body']['status'].update(payload_sha256='a'*64), 'grant_status_mismatch'),
                         (lambda d: d['body'].update(policy_sha256='a'*64), 'grant_status_mismatch'),
                         (lambda d: d['body'].update(max_offline_seconds=61), 'grant_requires_new_state')]:
        modified = copy.deepcopy(body)
        change(modified)
        with pytest.raises(GateError) as error:
            gate['store'].accept(gate['binding'], token(seed, modified, 'test-validity'), 'capability_grant')
        assert error.value.code == code


def test_restricted_and_missing_capability(gate):
    status, _ = proofs(gate, sequence=2, state='restricted')
    gate['store'].accept(gate['binding'], status, 'status_snapshot')
    assert decision(gate)['reason'] == 'restricted'
    assert gate['store'].decide(gate['binding'], 'not-present', gate['clock'])['reason'] == 'capability_not_granted'


def test_missing_or_corrupt_store_not_recreated(gate):
    store = gate['store']
    store.path.unlink()
    assert decision(gate)['reason'] == 'storage_error'
    assert not store.path.exists()
    with pytest.raises(GateError, match='unknown'):
        ValidityStore(store.root, gate['context'][2], gate['policy'])
    store.path.write_bytes(b'broken')
    assert decision(gate)['reason'] == 'storage_error'
    assert store.path.read_bytes() == b'broken'


def test_failed_state_commit_preserves_previous_gate(gate, monkeypatch):
    def failure():
        raise sqlite3.OperationalError('injected commit failure')
    monkeypatch.setattr(gate['store'], '_before_commit', failure)
    revoked, _ = proofs(gate, sequence=2, state='revoked')
    with pytest.raises(sqlite3.OperationalError):
        gate['store'].accept(gate['binding'], revoked, 'status_snapshot')
    assert decision(gate)['reason'] == 'storage_error'
    # This process latches failure; no successful gate after failed persistence.


def test_open_file_session_revoked_without_spatial_fallback(gate):
    files = FilePackages(gate['tmp'] / 'files')
    installed = files.install('examples/agent-runtime', 'examples/indoor-spatial')
    files.activate(gate['binding']['scene_id'], installed['package_sha256'], 0)
    session = GuardedSession(files, gate['binding']['scene_id'], gate['store'], gate['binding'], gate['clock'])
    assert session.query([1,0,1])['state'] == 'observed_free'
    revoked, _ = proofs(gate, sequence=2, state='revoked')
    gate['store'].accept(gate['binding'], revoked, 'status_snapshot')
    with pytest.raises(GateError, match='revoked'):
        session.query([1,0,1])
    session.close()
    with pytest.raises(GateError, match='closed'):
        session.query([1,0,1])


def test_independent_process_state_competition_and_precommit_exit(gate):
    store = gate['store']
    payload = gate['tmp'] / 'request.json'
    a, _ = proofs(gate, sequence=2)
    b, _ = proofs(gate, sequence=2, state='restricted')
    payload.write_bytes(canonical({'trust':gate['context'][1], 'policy':vars(gate['policy']), 'binding':gate['binding'], 'a':a, 'b':b}))
    code = '''
import sys,os
from pathlib import Path
from packages.service.sample import read_json
from experiments.scripts.trust_proof import load_test_trust
from experiments.scripts.validity_probe import ValidityStore,Policy,GateError
d=read_json(Path(sys.argv[2]).read_bytes())
s=ValidityStore(sys.argv[1],load_test_trust(__import__('json').dumps(d['trust']).encode()),Policy(**d['policy']))
if sys.argv[3]=='crash':
 s._before_commit=lambda:os._exit(74)
 name='a'
else: name=sys.argv[3]
try: s.accept(d['binding'],d[name],'status_snapshot')
except GateError as error:
 print(error.code)
 sys.exit(2)
'''
    processes = [subprocess.Popen([sys.executable,'-c',code,str(store.root),str(payload),name],stdout=subprocess.PIPE) for name in ('a','b')]
    results = [p.communicate(timeout=20)[0] for p in processes]
    assert sorted(p.returncode for p in processes) == [0,2]
    assert any(b'state_conflict' in result for result in results)
    request = json.loads(payload.read_text())
    request['a'] = proofs(gate, sequence=3)[0]
    payload.write_bytes(canonical(request))
    crashed = subprocess.run([sys.executable,'-c',code,str(store.root),str(payload),'crash'],timeout=20)
    assert crashed.returncode == 74
    assert decision(gate)['reason'] == 'storage_error'
    reopened = ValidityStore(store.root, gate['context'][2], gate['policy'])
    assert reopened.decide(gate['binding'], CAP, gate['clock'])['reason'] == 'storage_error'


def test_context_change_bootstrap_overwrite_and_binding_isolation(gate):
    store = gate['store']
    with pytest.raises(FileExistsError):
        ValidityStore(store.root, gate['context'][2], gate['policy'], bootstrap=True)
    with pytest.raises(GateError, match='context'):
        ValidityStore(store.root, gate['context'][2], Policy('other','test-deployment',30,0,180))
    other = copy.deepcopy(gate['binding'])
    other['package_sha256'] = 'f'*64
    assert not store.decide(other, CAP, gate['clock'])['simulated_allowed']


def test_new_state_renewal_requires_matching_grant_and_time(gate):
    status, grant = proofs(gate, sequence=2, issued=120)
    gate['store'].accept(gate['binding'], status, 'status_snapshot')
    assert decision(gate)['reason'] == 'grant_missing'
    gate['store'].accept(gate['binding'], grant, 'capability_grant')
    assert decision(gate)['reason'] == 'not_yet_valid'
    gate['tick'][1] += 10
    assert decision(gate)['simulated_allowed']
    assert decision(gate)['deadline'] == 150


def test_content_required_and_corrupt_persisted_signature_rejected(gate):
    store = gate['store']
    with sqlite3.connect(store.path) as db:
        db.execute('UPDATE states SET content=NULL')
    assert decision(gate)['reason'] == 'validity_unknown'
    seed = gate['context'][0]
    store.accept(gate['binding'], token(seed, gate['content']), 'content_statement')
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE states SET status='invalid.jws.value'")
    assert decision(gate)['reason'] == 'invalid_proof'
