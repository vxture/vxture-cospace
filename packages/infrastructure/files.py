"""Bounded local sealing for trusted local CLI; not a hostile-user sandbox."""
import os
from pathlib import Path, PurePosixPath
import stat
from packages.data.imports import ImportError, canonical, sha
from packages.service.sample import read_json

MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def safe_path(path):
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ImportError('unsafe_path', 'links and reparse points are not supported')
    return path


def relative(name):
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts
            or str(path) != name or any(part.endswith(('.', ' ')) for part in path.parts)):
        raise ImportError('unsafe_path', 'invalid logical path')
    return path


def bounded_read(path):
    path = safe_path(path)
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ImportError('input_limit', 'file missing or exceeds synthetic file limit')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise ImportError('input_limit', 'file exceeds synthetic file limit')
    return raw


class LocalFiles:
    def __init__(self, root):
        self.root = safe_path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def stage(self, identity, source, expected):
        source = safe_path(source)
        if source.is_relative_to(self.root) or self.root.is_relative_to(source):
            raise ImportError('unsafe_path', 'source and storage roots overlap')
        raw = bounded_read(source / 'package.json')
        if sha(raw) != expected:
            raise ImportError('manifest_mismatch', 'source manifest differs from request')
        manifest = read_json(raw)
        from packages.data.structure import check_structure
        check_structure(manifest, 'package', 'package.json', 'cospace.synthetic-bundle/0.2')
        records = manifest['data']['files']
        if len(records) + 1 > 100 or len(raw) + sum(r['bytes'] for r in records) > MAX_TOTAL:
            raise ImportError('input_limit', 'synthetic dataset limit exceeded')
        names = ['package.json'] + [r['path'] for r in records]
        if ('dataset.json' in [name.casefold() for name in names]
                or len({str(relative(name)).casefold() for name in names}) != len(names)):
            raise ImportError('unsafe_path', 'duplicate or case-colliding logical paths')
        stage = safe_path(self.root / 'staging' / identity)
        stage.mkdir(parents=True, exist_ok=False)
        (stage / 'package.json').write_bytes(raw)
        total = len(raw)
        for record in records:
            name = relative(record['path'])
            content = bounded_read(source / name)
            total += len(content)
            if total > MAX_TOTAL:
                raise ImportError('input_limit', 'synthetic dataset limit exceeded')
            if len(content) != record['bytes'] or sha(content) != record['sha256']:
                raise ImportError('content_mismatch', 'copied member differs from declared bytes')
            target = stage / name
            safe_path(target).parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(content)
        return stage

    def seal(self, identity, manifest):
        source = safe_path(self.root / 'staging' / identity)
        destination = safe_path(self.root / 'datasets' / manifest['dataset_id'])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ImportError('immutable_conflict', 'dataset storage already exists')
        (source / 'dataset.json').write_bytes(canonical(manifest))
        source.rename(destination)

    def verify(self, manifest):
        root = safe_path(self.root / 'datasets' / manifest['dataset_id'])
        if bounded_read(root / 'dataset.json') != canonical(manifest):
            raise ImportError('content_corrupt', 'sealed dataset manifest mismatch')
        for member in manifest['members']:
            content = bounded_read(root / relative(member['path']))
            if len(content) != member['bytes'] or sha(content) != member['sha256']:
                raise ImportError('content_corrupt', 'sealed dataset member mismatch')
