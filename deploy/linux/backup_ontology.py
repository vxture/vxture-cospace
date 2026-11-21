"""Deployment checkpoint: consistent per-database copies, never runtime secrets."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile


DATABASES = ('ontology-group-configuration.sqlite3', 'ontology-authoring.sqlite3',
             'scene-ontology-links.sqlite3')
CONTROL_DATABASE = 'preview-lifecycle.sqlite3'


def checkpoint(root: Path, images: list) -> Path:
    root = root.resolve(strict=True)
    runtime = root / 'data/business/runtime/preview-directory'
    if runtime.resolve() != runtime or not runtime.is_dir():
        raise ValueError('runtime must be a physical directory')
    backups = root / 'backups'
    if backups.is_symlink():
        raise ValueError('backup directory must not be a symlink')
    backups.mkdir(mode=0o700, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix='ontology-predeploy-', dir=backups))
    manifest = {'complete': False, 'images': images, 'databases': {}}
    manifest_path = target / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    sources = [(name, runtime / name) for name in DATABASES]
    # Paused/retired publications must remain quarantined across rollback.
    sources.append((CONTROL_DATABASE, runtime.parent / CONTROL_DATABASE))
    for name, source in sources:
        if source.is_symlink():
            raise ValueError('database must not be a symlink')
        if not source.exists():
            manifest['databases'][name] = 'absent'
            continue
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=10)) as original:
            with closing(sqlite3.connect(target / name)) as copy:
                original.backup(copy)
                if copy.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    raise ValueError('backup integrity check failed')
        manifest['databases'][name] = 'verified'
    manifest['complete'] = True
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return target


if __name__ == '__main__':
    os.umask(0o077)
    # Select image metadata only; Docker environment values must never be logged.
    images = []
    for service in ('workbench', 'ifc-parser', 'ifc-worker'):
        result = subprocess.run(
            ['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=cospace',
             '--filter', f'label=com.docker.compose.service={service}'],
            check=True, capture_output=True, text=True)
        for container in result.stdout.split():
            inspected = subprocess.run(
                ['docker', 'inspect', '--format', '{{json .Image}}', container],
                check=True, capture_output=True, text=True)
            images.append({'service': service, 'image_id': json.loads(inspected.stdout)})
    if {item['service'] for item in images} != {'workbench', 'ifc-parser', 'ifc-worker'}:
        raise ValueError('all previous service images must be recorded')
    print('Ontology checkpoint verified:', checkpoint(Path('/srv/md0/cospace'), images))
