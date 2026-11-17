"""Bounded local evidence-byte checks, separate from meaning, identity and approval."""
import hashlib
import os
from pathlib import Path
import stat
from typing import Annotated

from pydantic import Field, TypeAdapter

from packages.spatial.scene_graph import Fixed, Identity
from packages.spatial.scene_identity import Digest, content_digest

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_REFERENCES = 2048


class EvidenceReference(Fixed):
    id: Identity
    sha256: Digest


References = TypeAdapter(Annotated[list[EvidenceReference], Field(min_length=1, max_length=MAX_REFERENCES)])
DigestValue = TypeAdapter(Digest)


def _stamp(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _regular(path):
    if path.is_symlink() or path.is_junction():
        raise ValueError('evidence_regular_file_required')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_FILE_BYTES:
        raise ValueError('evidence_file_budget_or_type')
    return info


def _hash_file(path, before):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        # Windows path stat and handle stat can expose different ctime values.
        # Compare ctime only within the same API, retaining inode/size/mtime across APIs.
        if _stamp(opened)[:4] != _stamp(before)[:4]:
            raise ValueError('evidence_changed_during_read')
        while block := stream.read(1024 * 1024):
            size += len(block)
            if size > before.st_size:
                raise ValueError('evidence_changed_during_read')
            digest.update(block)
        if _stamp(os.fstat(stream.fileno())) != _stamp(opened):
            raise ValueError('evidence_changed_during_read')
    if size != before.st_size or _stamp(_regular(path)) != _stamp(before):
        raise ValueError('evidence_changed_during_read')
    return digest.hexdigest()


def check_evidence_content(root, references, *, document_sha256):
    """Trusted caller supplies root and document pin; no paths come from a report.

    Files are <sha256>.bin, read once per distinct digest. The receipt records
    bytes checked during this call, not durable retention or factual truth.
    """
    pin = DigestValue.validate_python(document_sha256)
    refs = References.validate_python(references)
    if len({ref.id for ref in refs}) != len(refs):
        raise ValueError('evidence_duplicate_id')
    root = Path(root)
    if root.is_symlink() or root.is_junction() or not root.is_dir():
        raise ValueError('evidence_root_required')
    root = root.resolve()
    files = {}
    for ref in refs:
        if ref.sha256 not in files:
            path = root / (ref.sha256 + '.bin')
            files[ref.sha256] = (path, _regular(path))
    if sum(info.st_size for _, info in files.values()) > MAX_TOTAL_BYTES:
        raise ValueError('evidence_total_budget')
    for expected, (path, info) in files.items():
        if _hash_file(path, info) != expected:
            raise ValueError('evidence_content_changed')
    if any(_stamp(_regular(path)) != _stamp(info) for path, info in files.values()):
        raise ValueError('evidence_changed_during_read')
    receipt = {
        'profile': 'cospace.evidence-content-check/0.1', 'document_sha256': pin,
        'members': [ref.model_dump() | {'bytes': files[ref.sha256][1].st_size} for ref in refs],
        'unique_files': len(files), 'total_bytes': sum(info.st_size for _, info in files.values()),
        'content_integrity_checked': True, 'meaning_verified': False,
        'source_identity_verified': False, 'real_release_ready': False,
    }
    return receipt | {'receipt_sha256': content_digest(receipt)}
