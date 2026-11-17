import pytest

from packages.service.observation_admission import append_with_evidence
from packages.spatial.scene_identity import content_digest
from test_observation_journal import journal, report, resolve
from test_evidence_content import put


def test_admission_receipt_pins_scope_and_reports_with_atomic_idempotent_append(journal, tmp_path):
    store, scope, _ = journal
    root = tmp_path / 'evidence'
    ref = put(root)
    rows = [report(evidence_sha256=[ref['sha256']]),
            report('correction', value='open', supersedes='event-1', evidence_sha256=[ref['sha256']])]
    result = append_with_evidence(store, scope, rows, authenticated_producer='sensor-a', evidence_root=root)
    assert [row['sequence'] for row in result['records']] == [1, 2]
    canonical_rows = [row['report'] for row in result['records']]
    assert result['evidence_receipt']['document_sha256'] == content_digest({'scope': scope, 'reports': canonical_rows})
    assert result['evidence_receipt']['unique_files'] == 1
    retry = append_with_evidence(store, scope, rows, authenticated_producer='sensor-a', evidence_root=root)
    assert retry == result
    assert resolve(journal)['value'] == 'open'
    assert resolve(journal)['evidence_content_verified'] is False
    assert result['source_identity_verified'] is False
    assert result['clock_quality_verified'] is False
    assert result['real_release_ready'] is False


@pytest.mark.parametrize('failure', ['missing', 'digest', 'correction', 'producer', 'subject', 'scope'])
def test_failed_admission_leaves_entire_journal_unchanged(journal, tmp_path, failure):
    store, scope, _ = journal
    root = tmp_path / 'evidence'
    ref = put(root)
    rows = [report(evidence_sha256=[ref['sha256']]), report('second', evidence_sha256=[ref['sha256']])]
    authenticated = 'sensor-a'
    if failure == 'missing':
        rows[1]['evidence_sha256'] = ['e' * 64]
    elif failure == 'digest':
        (root / (ref['sha256'] + '.bin')).write_bytes(b'wrong')
    elif failure == 'correction':
        rows[1]['supersedes'] = 'not-found'
    elif failure == 'producer':
        authenticated = 'sensor-b'
    elif failure == 'subject':
        rows[1]['entity_id'] = 'unknown'
    else:
        scope = scope | {'organization': 'other-org'}
    before = store.path.read_bytes()
    with pytest.raises((ValueError, FileNotFoundError)):
        append_with_evidence(store, scope, rows, authenticated_producer=authenticated, evidence_root=root)
    assert store.path.read_bytes() == before


def test_evidence_is_rechecked_on_retry(journal, tmp_path):
    store, scope, _ = journal
    root = tmp_path / 'evidence'
    ref = put(root)
    rows = [report(evidence_sha256=[ref['sha256']])]
    append_with_evidence(store, scope, rows, authenticated_producer='sensor-a', evidence_root=root)
    before = store.path.read_bytes()
    (root / (ref['sha256'] + '.bin')).unlink()
    with pytest.raises(FileNotFoundError):
        append_with_evidence(store, scope, rows, authenticated_producer='sensor-a', evidence_root=root)
    assert store.path.read_bytes() == before
