import hashlib
import pytest

from packages.data.evidence_content import check_evidence_content
from packages.spatial.scene_identity import content_digest


def put(root, raw=b'synthetic evidence bytes'):
    root.mkdir(exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    (root / (digest + '.bin')).write_bytes(raw)
    return {'id': 'evidence-1', 'sha256': digest}


def test_receipt_binds_document_and_reference_ids_but_never_certifies_meaning(tmp_path, monkeypatch):
    ref = put(tmp_path)
    from packages.data import evidence_content as module
    original = module._hash_file
    reads = []

    def count(path, info):
        reads.append(path)
        return original(path, info)

    monkeypatch.setattr(module, '_hash_file', count)
    refs = [ref, ref | {'id': 'other-role'}]
    result = check_evidence_content(tmp_path, refs, document_sha256='a' * 64)
    assert len(reads) == 1
    assert result['unique_files'] == 1
    assert result['members'][1]['id'] == 'other-role'
    assert result['total_bytes'] == len(b'synthetic evidence bytes')
    assert result['receipt_sha256'] == content_digest({k: v for k, v in result.items() if k != 'receipt_sha256'})
    assert result['meaning_verified'] is False
    assert result['source_identity_verified'] is False
    assert result['real_release_ready'] is False
    changed = check_evidence_content(tmp_path, refs, document_sha256='b' * 64)
    assert changed['receipt_sha256'] != result['receipt_sha256']
    assert str(tmp_path) not in str(result)


@pytest.mark.parametrize('refs', [[], [{'id': '../path', 'sha256': 'a' * 64}],
                                [{'id': 'ok', 'sha256': '../outside'}],
                                [{'id': 'same', 'sha256': 'a' * 64}] * 2,
                                [{'id': 'ok', 'sha256': 'a' * 64, 'path': 'outside'}]])
def test_invalid_refs_fail_before_files_are_opened(tmp_path, refs):
    with pytest.raises(ValueError):
        check_evidence_content(tmp_path, refs, document_sha256='a' * 64)


def test_missing_replaced_empty_and_directory_members_fail(tmp_path):
    ref = put(tmp_path)
    path = tmp_path / (ref['sha256'] + '.bin')
    path.write_bytes(b'different bytes')
    with pytest.raises(ValueError, match='content_changed'):
        check_evidence_content(tmp_path, [ref], document_sha256='a' * 64)
    path.write_bytes(b'')
    with pytest.raises(ValueError, match='budget_or_type'):
        check_evidence_content(tmp_path, [ref], document_sha256='a' * 64)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        check_evidence_content(tmp_path, [ref], document_sha256='a' * 64)
    path.mkdir()
    with pytest.raises(ValueError, match='budget_or_type'):
        check_evidence_content(tmp_path, [ref], document_sha256='a' * 64)


def test_all_file_sizes_preflight_before_hashing(tmp_path, monkeypatch):
    from packages.data import evidence_content as module
    first = put(tmp_path)
    second = put(tmp_path, b'other') | {'id': 'evidence-2'}
    monkeypatch.setattr(module, 'MAX_TOTAL_BYTES', 3)
    monkeypatch.setattr(module, '_hash_file', lambda *args: pytest.fail('must reject before reading'))
    with pytest.raises(ValueError, match='total_budget'):
        check_evidence_content(tmp_path, [first, second], document_sha256='a' * 64)


def test_member_growth_and_set_changes_during_read_are_rejected(tmp_path, monkeypatch):
    from packages.data import evidence_content as module
    first = put(tmp_path)
    second = put(tmp_path, b'other') | {'id': 'evidence-2'}
    original = module._hash_file

    def changing(path, info):
        result = original(path, info)
        if path.name.startswith(second['sha256']):
            (tmp_path / (first['sha256'] + '.bin')).write_bytes(b'changed after hashing')
        return result

    monkeypatch.setattr(module, '_hash_file', changing)
    with pytest.raises(ValueError, match='changed_during_read'):
        check_evidence_content(tmp_path, [first, second], document_sha256='a' * 64)


def test_link_member_is_not_followed(tmp_path):
    ref = put(tmp_path)
    real = tmp_path / (ref['sha256'] + '.bin')
    moved = tmp_path / 'elsewhere'
    real.rename(moved)
    try:
        real.symlink_to(moved)
    except OSError:
        pytest.skip('symlink permission unavailable')
    with pytest.raises(ValueError, match='regular_file_required'):
        check_evidence_content(tmp_path, [ref], document_sha256='a' * 64)


def test_per_file_budget_and_reference_budget(tmp_path, monkeypatch):
    from packages.data import evidence_content as module
    ref = put(tmp_path)
    monkeypatch.setattr(module, 'MAX_FILE_BYTES', 2)
    with pytest.raises(ValueError, match='budget_or_type'):
        check_evidence_content(tmp_path, [ref], document_sha256='a' * 64)
    refs = [ref | {'id': f'e-{i}'} for i in range(2049)]
    with pytest.raises(ValueError):
        check_evidence_content(tmp_path, refs, document_sha256='a' * 64)
