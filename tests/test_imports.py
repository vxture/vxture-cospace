"""Import sealing, idempotency, failure visibility and PostgreSQL competition."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import SQLAlchemyError
from packages.data.imports import ImportManager, ImportError, sha
from packages.infrastructure.files import LocalFiles
from packages.infrastructure.imports import ImportStore, datasets
from packages.infrastructure.migrations import migrate_database
from scripts.build_sample import build


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        build(self.source, spatial=True)
        self.engine = create_engine(os.environ.get('COSPACE_TEST_DATABASE_URL', 'sqlite:///' + str(self.root / 'test.db')))
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.store = ImportStore(self.engine)
        self.files = LocalFiles(self.root / 'storage')
        self.manager = ImportManager(self.store, self.files)
        self.request = {'schema_version': 'cospace.import/0.1', 'scene_id': 'synthetic-equipment-corridor',
            'data_kind': 'synthetic', 'source_description': 'test synthetic fixture', 'purpose': 'synthetic_check',
            'usage_conditions': 'not_assessed', 'idempotency_key': uuid.uuid4().hex,
            'expected_manifest_sha256': sha((self.source / 'package.json').read_bytes())}

    def ingest(self):
        return self.manager.ingest(self.source, self.request, 'test-engineer')

    def test_sealed_dataset_source_independence_and_replay(self):
        result = self.ingest()
        self.assertEqual(result['state'], 'committed')
        dataset = self.manager.dataset(result['dataset_id'])
        self.assertEqual(len(dataset['manifest']['members']), 8)
        self.assertFalse(dataset['manifest']['algorithm_ready'])
        self.assertNotIn(str(self.root), str(dataset))
        (self.source / 'package.json').unlink()
        (self.source / 'objects.json').write_text('{}')
        self.assertEqual(self.ingest()['import_id'], result['import_id'])
        self.assertEqual(self.manager.dataset(result['dataset_id']), dataset)
        self.request['source_description'] = 'different claim'
        with self.assertRaisesRegex(ImportError, 'different request'):
            self.ingest()
        sealed = self.files.root / 'datasets' / result['dataset_id'] / 'objects.json'
        sealed.write_text('{}')
        with self.assertRaisesRegex(ImportError, 'member mismatch'):
            self.manager.dataset(result['dataset_id'])

    def test_rejected_content_and_no_dataset(self):
        (self.source / 'objects.json').write_text('{}')
        with self.assertRaises(ImportError):
            self.ingest()
        result = self.ingest()
        self.assertEqual(result['state'], 'rejected')
        self.assertIsNone(result['dataset_id'])
        self.assertEqual(result['diagnostic']['code'], 'content_mismatch')

    def test_limits_overlap_and_case_collision(self):
        from packages.service.sample import read_json
        import json
        manifest = read_json((self.source / 'package.json').read_bytes())
        for mode in ('limit', 'collision', 'traversal'):
            with self.subTest(mode=mode):
                changed = json.loads(json.dumps(manifest))
                if mode == 'limit': changed['data']['files'][0]['bytes'] = 40 * 1024 * 1024
                if mode == 'collision': changed['data']['files'][1]['path'] = 'ONTOLOGY.JSON'
                if mode == 'traversal': changed['data']['files'][0]['path'] = '../outside.json'
                raw = json.dumps(changed).encode()
                (self.source / 'package.json').write_bytes(raw)
                self.request.update(idempotency_key=uuid.uuid4().hex, expected_manifest_sha256=sha(raw))
                with self.assertRaises(ImportError): self.ingest()
        self.request.update(idempotency_key=uuid.uuid4().hex)
        overlap = ImportManager(self.store, LocalFiles(self.source / 'nested'))
        with self.assertRaises(ImportError): overlap.ingest(self.source, self.request, 'actor')

    def test_database_commit_failure_leaves_no_visible_dataset(self):
        with self.engine.connect() as conn:
            before = conn.execute(select(func.count()).select_from(datasets)).scalar_one()
        with patch.object(self.store, 'commit', side_effect=SQLAlchemyError('injected')):
            with self.assertRaises(SQLAlchemyError): self.ingest()
        record = self.ingest()
        self.assertEqual(record['state'], 'validating')
        self.assertIsNone(record['dataset_id'])
        self.assertEqual(len(list((self.files.root / 'datasets').iterdir())), 1)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(func.count()).select_from(datasets)).scalar_one(), before)

    def test_reparse_source_rejected(self):
        # Windows directory junction does not require developer-mode symlink privilege.
        link = self.root / 'junction'
        if os.name == 'nt':
            import subprocess
            completed = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(self.source)], capture_output=True)
            self.assertEqual(completed.returncode, 0)
        else:
            link.symlink_to(self.source, target_is_directory=True)
        try:
            with self.assertRaises(ImportError) as caught:
                self.manager.ingest(link, self.request, 'actor')
            self.assertEqual(caught.exception.code, 'unsafe_path')
        finally:
            if os.name == 'nt': link.rmdir()
            else: link.unlink()

    def test_postgresql_concurrent_idempotency(self):
        if self.engine.dialect.name != 'postgresql':
            self.skipTest('PostgreSQL concurrency requires isolated database')
        barrier = threading.Barrier(2)
        def ingest(_):
            barrier.wait(timeout=5)
            return self.ingest()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(ingest, range(2)))
        self.assertEqual(results[0]['import_id'], results[1]['import_id'])
        final = self.ingest()
        self.assertEqual(final['state'], 'committed')
        self.assertEqual(len(list((self.files.root / 'datasets').iterdir())), 1)

    def test_import_success_and_failure_do_not_change_current_release(self):
        from packages.infrastructure.releases import ReleaseStore
        from packages.lifecycle.releases import ReleaseManager
        scene = 'import-pointer-' + uuid.uuid4().hex
        def mutate(name, doc):
            if 'scene_id' in doc: doc['scene_id'] = scene
            if 'source_truth' in doc: doc['source_truth'] = {**doc['source_truth'], 'scene_id': scene}
        self.source = self.root / 'pointer-source'
        build(self.source, mutate, spatial=True)
        self.request.update(scene_id=scene, expected_manifest_sha256=sha((self.source / 'package.json').read_bytes()))
        releases = ReleaseManager(ReleaseStore(self.engine))
        registered = releases.register(self.source)
        releases.activate(scene, registered['release_id'], 0, 'engineer')
        before = releases.current(scene)
        self.ingest()
        self.assertEqual(releases.current(scene), before)
        self.request['idempotency_key'] = uuid.uuid4().hex
        (self.source / 'objects.json').write_text('{}')
        with self.assertRaises(ImportError): self.ingest()
        self.assertEqual(releases.current(scene), before)
