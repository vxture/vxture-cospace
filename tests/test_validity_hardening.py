"""R2b second increment: delegated scope, durable intents and race ordering."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import copy
import secrets
import sqlite3
import threading

import pytest
from experiments.scripts.delegation_probe import load_delegation
from experiments.scripts.trust_proof import ProofError
from experiments.scripts.validity_probe import ValidityStore, GateError
from tests.test_validity_probe import gate, proofs, decision, CAP
from tests.test_trust_proof import native_sign, token


def delegated(gate, tmp_path, change=None):
    root_seed = secrets.token_hex(32)
    root_pub = bytes.fromhex(native_sign(root_seed, b'')['public_key'])
    doc = {'schema_version':'cospace.test-delegation/0.1','test_only':True,
           'deployment_id':'test-deployment','version':1,'keys':[]}
    for key in gate['context'][1]['keys']:
        doc['keys'].append({**key, 'scenes':[gate['binding']['scene_id']],
                            'not_before':0,'expires_at':125,'revoked':False})
    if change:
        change(doc)
    header = {'alg':'EdDSA','typ':'cospace-test-delegation+jws','kid':'test-root','version':'0.1'}
    certificate = token(root_seed, doc, header=header)
    trust = load_delegation(certificate, {'test-root':root_pub}, expected_deployment='test-deployment', expected_version=1)
    return trust, certificate, root_pub


def install_proofs(gate, store):
    seed = gate['context'][0]
    store.accept(gate['binding'], token(seed,gate['content']), 'content_statement')
    status, grant_proof = proofs(gate)
    store.accept(gate['binding'],status,'status_snapshot')
    store.accept(gate['binding'],grant_proof,'capability_grant')


def test_root_delegate_limits_gate_deadline(gate, tmp_path):
    trust, _, _ = delegated(gate,tmp_path)
    store = ValidityStore(tmp_path/'delegated',trust,gate['policy'],bootstrap=True)
    install_proofs(gate,store)
    result=store.decide(gate['binding'],CAP,gate['clock'])
    assert result['simulated_allowed'] and result['deadline']==125
    gate['tick'][1]+=15
    assert store.decide(gate['binding'],CAP,gate['clock'])['reason']=='expired'


@pytest.mark.parametrize('change,code', [
    (lambda d:d['keys'][0].update(scenes=['other-scene']), 'key_scope_or_revocation'),
    (lambda d:d['keys'][0].update(revoked=True), 'key_scope_or_revocation'),
    (lambda d:d['keys'][0].update(not_before=101), 'key_interval_mismatch'),
    (lambda d:d['keys'][0].update(roles=['validity']), 'invalid_proof')])
def test_delegated_restrictions_reject_signed_content(gate,tmp_path,change,code):
    trust,_,_=delegated(gate,tmp_path,change)
    store=ValidityStore(tmp_path/'restricted',trust,gate['policy'],bootstrap=True)
    with pytest.raises(GateError) as error:
        install_proofs(gate,store)
    assert error.value.code==code


def test_delegation_forgery_version_deployment_and_duplicates(gate,tmp_path):
    _,certificate,pub=delegated(gate,tmp_path)
    for roots,deployment,version in [({'test-root':bytes.fromhex(native_sign(secrets.token_hex(32),b'')['public_key'])},'test-deployment',1),
                                     ({'test-root':pub},'other',1),({'test-root':pub},'test-deployment',2)]:
        with pytest.raises(ProofError):
            load_delegation(certificate,roots,expected_deployment=deployment,expected_version=version)
    with pytest.raises(ProofError,match='duplicate'):
        delegated(gate,tmp_path,lambda d:d['keys'].append(copy.deepcopy(d['keys'][0])))


def test_failed_persistence_blocks_already_open_and_reopened_store(gate,monkeypatch):
    original=gate['store']
    other=ValidityStore(original.root,gate['context'][2],gate['policy'])
    def fail():raise sqlite3.OperationalError('injected transaction failure')
    monkeypatch.setattr(original,'_before_commit',fail)
    revoked,_=proofs(gate,sequence=2,state='revoked')
    with pytest.raises(sqlite3.OperationalError):
        original.accept(gate['binding'],revoked,'status_snapshot')
    for store in (original,other,ValidityStore(original.root,gate['context'][2],gate['policy'])):
        assert store.decide(gate['binding'],CAP,gate['clock'])['reason']=='storage_error'
    assert list(original.pending.iterdir())


def test_rejected_logical_proof_leaves_no_fault_marker(gate):
    status,_=proofs(gate,sequence=1,state='restricted')
    with pytest.raises(GateError,match='state_conflict'):
        gate['store'].accept(gate['binding'],status,'status_snapshot')
    assert not list(gate['store'].pending.iterdir())
    assert decision(gate)['simulated_allowed']


def test_query_snapshot_and_revocation_commit_have_defined_order(gate):
    reader=gate['store']
    writer=ValidityStore(reader.root,gate['context'][2],gate['policy'])
    selected, release, writer_ready = threading.Event(),threading.Event(),threading.Event()
    def pause_read():
        selected.set()
        assert release.wait(10)
    reader._decision_snapshot=pause_read
    writer._before_commit=lambda:writer_ready.set()
    revoked,_=proofs(gate,sequence=2,state='revoked')
    with ThreadPoolExecutor(2) as pool:
        old=pool.submit(reader.decide,gate['binding'],CAP,gate['clock'])
        try:
            assert selected.wait(10)
            update=pool.submit(writer.accept,gate['binding'],revoked,'status_snapshot')
            assert writer_ready.wait(10)
        finally:
            release.set()
        assert old.result(timeout=10)['simulated_allowed']
        update.result(timeout=10)
    reader._decision_snapshot=lambda:None
    assert reader.decide(gate['binding'],CAP,gate['clock'])['reason']=='revoked'


def test_delegate_configuration_changes_cannot_silently_reopen_ledger(gate,tmp_path):
    trust,_,_=delegated(gate,tmp_path)
    store=ValidityStore(tmp_path/'bound-trust',trust,gate['policy'],bootstrap=True)
    changed=dict(trust)
    changed['test-publisher']=replace(changed['test-publisher'],revoked=True)
    with pytest.raises(GateError,match='trust_context_changed'):
        ValidityStore(store.root,changed,gate['policy'])


def test_delegation_schema_and_pending_write_failure(gate,monkeypatch):
    import json
    from jsonschema import Draft202012Validator
    from experiments.scripts.trust_proof import SCHEMA
    Draft202012Validator.check_schema(json.loads(SCHEMA.with_name('test-delegation-v0.1.schema.json').read_text()))
    original=type(gate['store'].pending).open
    def fail_marker(path,*args,**kwargs):
        if path.parent==gate['store'].pending:
            raise PermissionError('injected intent write failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(type(gate['store'].pending),'open',fail_marker)
    revoked,_=proofs(gate,sequence=2,state='revoked')
    with pytest.raises(PermissionError):
        gate['store'].accept(gate['binding'],revoked,'status_snapshot')
    assert decision(gate)['reason']=='storage_error'
