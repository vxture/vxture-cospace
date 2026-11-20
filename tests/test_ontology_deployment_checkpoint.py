import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest


spec = importlib.util.spec_from_file_location(
    'ontology_checkpoint', Path(__file__).resolve().parents[1] / 'deploy/linux/backup_ontology.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_wal_backup_can_restore_committed_definition_without_changing_source(tmp_path):
    runtime = tmp_path / 'data/business/runtime/preview-directory'
    runtime.mkdir(parents=True)
    source = runtime / module.DATABASES[1]
    with sqlite3.connect(source) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('CREATE TABLE revisions (id INTEGER, definition TEXT)')
        writer.execute("INSERT INTO revisions VALUES (1, 'frozen-definition')")
        writer.commit()
        target = module.checkpoint(tmp_path, [{'service': 'workbench', 'image_id': 'sha256:old'}])
        writer.execute("INSERT INTO revisions VALUES (2, 'later-definition')")
        writer.commit()
        with sqlite3.connect(target / source.name) as restored:
            assert restored.execute('SELECT * FROM revisions').fetchall() == [(1, 'frozen-definition')]
        assert writer.execute('SELECT COUNT(*) FROM revisions').fetchone() == (2,)
    manifest = json.loads((target / 'manifest.json').read_text())
    assert manifest['complete'] is True
    assert manifest['databases'][module.DATABASES[0]] == 'absent'
    assert manifest['images'][0]['image_id'] == 'sha256:old'


def test_corrupt_database_blocks_deployment_with_incomplete_checkpoint(tmp_path):
    runtime = tmp_path / 'data/business/runtime/preview-directory'
    runtime.mkdir(parents=True)
    (runtime / module.DATABASES[0]).write_bytes(b'corrupt database')
    with pytest.raises(sqlite3.DatabaseError):
        module.checkpoint(tmp_path, [])
    manifests = list((tmp_path / 'backups').glob('*/manifest.json'))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text())['complete'] is False
