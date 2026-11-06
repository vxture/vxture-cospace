"""Expose archive members as inert text for credential scanning, including DOCX.

Never execute members or restore their paths/permissions. Output names are flat;
an index maps them back to source members. Fail closed on depth/size limits.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

MAX_BYTES = 256 * 1024 * 1024
MAX_FILES = 20000
MAX_DEPTH = 3
SUFFIXES = ('.zip', '.docx', '.xlsx', '.pptx', '.tgz', '.tar.gz', '.tar')


def expand_archives(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    archives = [p for p in root.rglob('*') if p.is_file() and not p.is_symlink()
                and p.name.lower().endswith(SUFFIXES) and not p.is_relative_to(destination)]
    destination.mkdir(parents=True, exist_ok=False)
    index = {}
    total = 0

    def unpack(raw, name, depth):
        nonlocal total
        if depth > MAX_DEPTH:
            raise ValueError('archive_scan_depth_limit')
        if zipfile.is_zipfile(io.BytesIO(raw)):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for item in archive.infolist():
                    if item.is_dir():
                        continue
                    if item.file_size > MAX_BYTES - total:
                        raise ValueError('archive_scan_size_limit')
                    with archive.open(item) as stream:
                        member(stream.read(MAX_BYTES - total + 1), name + '!' + item.filename, depth)
        else:
            with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
                for item in archive:
                    if item.isdir():
                        continue
                    if item.islnk():
                        # Vendor npm tarballs may share declarations by hard link.
                        # The regular target is scanned independently; expose the
                        # link metadata without creating a filesystem link.
                        target = archive.getmember(item.linkname)
                        if not target.isfile():
                            raise ValueError('archive_scan_invalid_link_target')
                        member(item.linkname.encode(), name + '!' + item.name, depth)
                        continue
                    if not item.isfile():
                        raise ValueError('archive_scan_special_member')
                    if item.size > MAX_BYTES - total:
                        raise ValueError('archive_scan_size_limit')
                    with archive.extractfile(item) as stream:
                        member(stream.read(MAX_BYTES - total + 1), name + '!' + item.name, depth)

    def member(raw, name, depth):
        nonlocal total
        total += len(raw)
        if total > MAX_BYTES or len(index) >= MAX_FILES:
            raise ValueError('archive_scan_resource_limit')
        identity = hashlib.sha256(name.encode()).hexdigest() + '.txt'
        if identity in index:
            raise ValueError('archive_scan_duplicate_member')
        # Gitleaks has a built-in DOCX/binary extension skip. Flatten to .txt so
        # XML/JSON/code members are actually inspected instead of silently skipped.
        (destination / identity).write_bytes(raw)
        index[identity] = name
        if name.lower().endswith(SUFFIXES):
            unpack(raw, name, depth + 1)

    for path in archives:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('archive_scan_size_limit')
        unpack(path.read_bytes(), path.relative_to(root).as_posix(), 1)
    # Separate hash and source fields: a JSON mapping of hash -> token filename
    # resembles an API-key assignment to generic credential detectors.
    manifest = [{'id': identity, 'source': name} for identity, name in index.items()]
    (destination / 'archive-index.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return index


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    result = expand_archives(args.root, args.destination)
    print(f'Archive members exposed for scanning: {len(result)}')
