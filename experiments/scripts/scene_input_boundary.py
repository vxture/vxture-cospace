"""Read only a bounded file inside a separately configured local source root."""
from pathlib import Path


def read_source(path, *, root, suffix, max_bytes):
    if root is None:
        raise ValueError('source_root_not_configured')
    allowed = Path(root).resolve(strict=True)
    source = Path(path).resolve(strict=True)
    if not allowed.is_dir() or not source.is_relative_to(allowed):
        raise ValueError('source_outside_allowed_root')
    if not source.is_file() or source.suffix.lower() != suffix:
        raise ValueError('source_type_invalid')
    with source.open('rb') as stream:
        raw = stream.read(max_bytes+1)
    if len(raw) > max_bytes:
        raise ValueError('document_byte_budget')
    return raw
