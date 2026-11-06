"""Content references for the experimental synthetic package profile."""
import hashlib
from pathlib import Path, PurePosixPath


def verify_files(root, records):
    root = Path(root).resolve()
    if not isinstance(records, list) or not records:
        raise ValueError('data.files must be a nonempty list')
    verified = {}
    for record in records:
        name = record['path']
        relative = PurePosixPath(name)
        if (not name or '\\' in name or ':' in name or relative.is_absolute()
                or '..' in relative.parts):
            raise ValueError(f'invalid package path: {name}')
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'missing or out-of-package file: {name}')
        if name in verified:
            raise ValueError(f'duplicate content reference: {name}')
        raw = path.read_bytes()
        if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError(f'content integrity mismatch: {name}')
        if record['media_type'] != 'application/json':
            raise ValueError('sample profile only supports application/json')
        verified[name] = raw
    return verified
