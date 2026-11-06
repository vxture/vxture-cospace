"""Persistent lifecycle semantics. SQLite is single-thread test-only storage."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

from sqlalchemy import create_engine, select, update
from fastapi.testclient import TestClient

from apps.api.managed import create_managed_app

from packages.infrastructure.releases import ReleaseStore, events, releases
from packages.lifecycle.releases import ReleaseError, ReleaseManager
from packages.service.query import QueryError
from scripts.build_sample import build


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scene = 'test-' + uuid.uuid4().hex
        self.url = os.environ.get('COSPACE_TEST_DATABASE_URL', 'sqlite:///' + str(self.root / 'state.db'))
        self.engine = create_engine(self.url)
        self.addCleanup(self.engine.dispose)
        self.store = ReleaseStore(self.engine)
        self.store.initialize_demo()
        self.manager = ReleaseManager(self.store)
        self.packages = {}
        for version in ('a', 'b'):
            path = self.root / version
            def mutate(name, doc):
                if 'scene_id' in doc:
                    doc['scene_id'] = self.scene
                if 'source_truth' in doc:
                    doc['source_truth'] = {**doc['source_truth'], 'scene_id': self.scene}
                if name == 'release.json':
                    doc['release_id'] = version
            build(path, mutate, spatial=True)
            self.packages[version] = path
            self.manager.register(path)

    def query(self, version='a'):
        return self.manager.query(self.scene, version, 'sample-local', [1, 0, 1])

    def test_switch_conflict_history_and_restart(self):
        self.assertEqual(self.manager.activate(self.scene, 'a', 0, 'engineer')['revision'], 1)
        self.assertEqual(self.manager.activate(self.scene, 'b', 1, 'engineer')['revision'], 2)
        with self.assertRaisesRegex(ReleaseError, 'revision changed'):
            self.manager.activate(self.scene, 'a', 1, 'stale')
        self.assertEqual(self.manager.current(self.scene)['release_id'], 'b')
        self.assertEqual(self.query('a')['release_id'], 'a')
        other = create_engine(self.url)
        try:
            restarted = ReleaseManager(ReleaseStore(other))
            self.assertEqual(restarted.current(self.scene)['revision'], 2)
            self.assertEqual(restarted.query(self.scene, 'a', 'sample-local', [1, 0, 1])['state'], 'observed_free')
        finally:
            other.dispose()

    def test_revocation_blocks_pinned_and_rollback_but_keeps_trace(self):
        self.manager.activate(self.scene, 'a', 0, 'engineer')
        self.manager.activate(self.scene, 'b', 1, 'engineer')
        self.manager.revoke(self.scene, 'a', 'reviewer', 'test defect')
        for operation in (lambda: self.query('a'), lambda: self.manager.activate(self.scene, 'a', 2, 'engineer')):
            with self.assertRaises(QueryError) as caught:
                operation()
            self.assertEqual(caught.exception.code, 'capability_revoked')
        trace = self.manager.trace(self.scene, 'a')
        self.assertEqual(trace['revocations'][0]['reason'], 'test defect')
        self.assertEqual(self.manager.current(self.scene)['release_id'], 'b')

    def test_current_revoked_does_not_silently_fallback(self):
        self.manager.activate(self.scene, 'a', 0, 'engineer')
        self.manager.revoke(self.scene, 'a', 'reviewer', 'bad evidence')
        self.assertFalse(self.manager.current(self.scene)['active'])
        with self.assertRaises(QueryError):
            self.query()

    def test_snapshot_does_not_depend_on_original_files(self):
        (self.packages['a'] / 'coverage.json').write_text('{}')
        self.assertEqual(self.query()['state'], 'observed_free')
        with self.assertRaises(ValueError):
            self.manager.register(self.packages['a'])

    def test_identity_immutable_and_duplicate_registration_idempotent(self):
        self.manager.register(self.packages['a'])
        third = self.root / 'changed'
        def mutate(name, doc):
            if 'scene_id' in doc:
                doc['scene_id'] = self.scene
            if 'source_truth' in doc:
                doc['source_truth'] = {**doc['source_truth'], 'scene_id': self.scene}
            if name == 'release.json':
                doc['release_id'] = 'a'
            if name == 'coverage.json':
                doc['evidence'][0]['description'] = 'different content'
        build(third, mutate, spatial=True)
        with self.assertRaises(ReleaseError) as caught:
            self.manager.register(third)
        self.assertEqual(caught.exception.code, 'immutable_conflict')

    def test_transaction_failure_rolls_back_pointer_and_event(self):
        with self.assertRaises(RuntimeError):
            with self.store.transaction(self.scene) as tx:
                tx.activate('a', 'engineer')
                raise RuntimeError('simulate failure before commit')
        with self.store.transaction(self.scene) as tx:
            self.assertEqual(tx.current(), {'release_id': None, 'revision': 0})
        with self.engine.connect() as conn:
            self.assertIsNone(conn.execute(select(events).where(events.c.scene_id == self.scene)).first())

    def test_new_release_cannot_relabel_modified_truth_as_same_version(self):
        third = self.root / 'new-release-changed-truth'
        def mutate(name, doc):
            if 'scene_id' in doc:
                doc['scene_id'] = self.scene
            if 'source_truth' in doc:
                doc['source_truth'] = {**doc['source_truth'], 'scene_id': self.scene}
            if name == 'release.json':
                doc['release_id'] = 'third'
            if name == 'coverage.json':
                doc['evidence'][0]['description'] = 'new observation'
        build(third, mutate, spatial=True)
        with self.assertRaisesRegex(ReleaseError, 'truth identity'):
            self.manager.register(third)

    def test_missing_version_and_reason_leave_state_unchanged(self):
        for operation in (lambda: self.manager.activate(self.scene, 'missing', 0, 'engineer'),
                          lambda: self.manager.revoke(self.scene, 'a', 'reviewer', ' ')):
            with self.assertRaises(ReleaseError):
                operation()
        with self.store.transaction(self.scene) as tx:
            self.assertEqual(tx.current()['revision'], 0)

    def test_stored_content_corruption_is_error_not_unknown(self):
        with self.engine.begin() as conn:
            conn.execute(update(releases).where(releases.c.scene_id == self.scene, releases.c.release_id == 'a')
                         .values(payload={'broken': True}))
        with self.assertRaises(ReleaseError) as caught:
            self.query()
        self.assertEqual(caught.exception.code, 'content_corrupt')

    def test_managed_api_checks_revocation_and_keeps_history(self):
        self.manager.activate(self.scene, 'a', 0, 'engineer')
        with TestClient(create_managed_app(self.manager)) as client:
            self.assertEqual(client.get(f'/scenes/{self.scene}/current').json()['release_id'], 'a')
            request = dict(scene_id=self.scene, release_id='a', frame_id='sample-local', point=[1, 0, 1])
            self.assertEqual(client.post('/query', json=request).json()['state'], 'observed_free')
            self.manager.revoke(self.scene, 'a', 'reviewer', 'runtime defect')
            response = client.post('/query', json=request)
            self.assertEqual(response.status_code, 410)
            self.assertEqual(response.json()['detail']['code'], 'capability_revoked')
            history = client.get(f'/scenes/{self.scene}/releases/a')
            self.assertEqual(history.status_code, 200)
            self.assertEqual(history.json()['revocations'][0]['reason'], 'runtime defect')
            self.assertEqual(client.get(f'/scenes/{self.scene}/releases/missing').status_code, 404)

    def test_snapshot_export_cannot_mutate_service(self):
        from packages.service.query import SampleService
        service = SampleService(self.packages['a'])
        exported = service.export_snapshot()
        exported['snapshot']['coverage']['regions'].clear()
        self.assertEqual(service.query(self.scene, 'a', 'sample-local', [1, 0, 1])['state'], 'observed_free')

    def test_workbench_static_assets_same_origin_and_no_write_routes(self):
        assets = self.root / 'workbench'
        assets.mkdir()
        (assets / 'index.html').write_text('<html>workbench</html>')
        with TestClient(create_managed_app(self.manager, workbench_dir=assets)) as client:
            self.assertEqual(client.get('/workbench/').text, '<html>workbench</html>')
            self.assertEqual(client.post('/activate').status_code, 404)
            self.assertEqual(client.get('/workbench/../state.db').status_code, 404)

    def test_human_cells_match_query_policy_and_revocation(self):
        from packages.spatial.coverage import contains
        with TestClient(create_managed_app(self.manager)) as client:
            url = f'/scenes/{self.scene}/releases/a/human'
            response = client.get(url)
            self.assertEqual(response.status_code, 200)
            view = response.json()
            self.assertEqual(view['release_id'], 'a')
            self.assertEqual(len(view['objects']), 3)
            for point, state, reason in [([5, 3, 1], 'occupied', 'synthetic_observation'),
                                          ([8, 4, 1], 'unknown', 'unobserved'),
                                          ([3.5, .5, .5], 'unknown', 'conflict'),
                                          ([1, 0, 1], 'observed_free', 'synthetic_observation')]:
                hit = [c for c in view['cells'] if contains(c['bounds'], point)]
                self.assertEqual(len(hit), 1)
                self.assertEqual((hit[0]['state'], hit[0]['reason']), (state, reason))
            for cell in view['cells']:
                center = [(a+b)/2 for a, b in zip(*cell['bounds'])]
                query = self.manager.query(self.scene, 'a', view['frame_id'], center)
                for field in ('state', 'reason', 'evidence_ids'):
                    self.assertEqual(cell[field], query[field])
            self.manager.revoke(self.scene, 'a', 'reviewer', 'preview defect')
            self.assertEqual(client.get(url).status_code, 410)
            self.assertEqual(client.get(f'/scenes/{self.scene}/releases/missing/human').status_code, 404)

    def test_human_snapshot_detached_and_legacy_explicit(self):
        from packages.service.query import SampleService
        service = SampleService(self.packages['a'])
        view = service.human()
        view['objects'].clear()
        self.assertEqual(len(service.human()['objects']), 3)
        payload = service.export_snapshot()
        payload['snapshot'].pop('human_view')
        legacy = SampleService.from_snapshot(payload)
        with self.assertRaisesRegex(QueryError, 'legacy snapshot'):
            legacy.human()
        self.assertEqual(legacy.query(self.scene, 'a', 'sample-local', [1, 0, 1])['state'], 'observed_free')

    def test_inspection_api_fixed_sources_detached_and_revoked(self):
        import hashlib
        self.manager.activate(self.scene, 'a', 0, 'engineer')
        original = (self.packages['a'] / 'ontology.json').read_bytes()
        # The fixed projection must survive loss or modification of source files.
        (self.packages['a'] / 'ontology.json').write_text('{}')
        (self.packages['a'] / 'package.json').unlink()
        with TestClient(create_managed_app(self.manager)) as client:
            base = f'/scenes/{self.scene}/releases/a'
            data = client.get(base + '/data').json()
            ontology = client.get(base + '/ontology').json()
            fixed = self.manager.current(self.scene)
            for result in (data, ontology):
                for field in ('scene_id', 'release_id', 'truth_version_id', 'frame_id', 'package_sha256'):
                    self.assertEqual(result[field], fixed[field])
            self.assertEqual(len(data['items']), 7)
            self.assertEqual(data['verification']['verified_at'], None)
            self.assertFalse(data['verification']['source_files_rechecked'])
            self.assertEqual(data['usage_conditions'], 'not_assessed')
            self.assertEqual(data['field_quality'], 'not_field_validated')
            self.assertEqual({item['role'] for item in data['items']},
                             {'ontology', 'objects', 'coverage', 'truth', 'human_view', 'machine_view', 'release'})
            self.assertNotIn(str(self.root), str(data))
            self.assertEqual(ontology['ontology_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(ontology['validation']['object_count'], 3)
            self.assertEqual(ontology['definition']['types']['cabinet']['properties']['name'],
                             {'type': 'string', 'required': True})
            self.assertTrue(all(obj['evidence_ids'] is None for obj in ontology['objects']))
            ontology['definition']['types'].clear()
            data['items'].clear()
            self.assertEqual(len(client.get(base + '/data').json()['items']), 7)
            self.assertEqual(len(client.get(base + '/ontology').json()['definition']['types']), 3)
            self.manager.revoke(self.scene, 'a', 'reviewer', 'inspection defect')
            for kind in ('data', 'ontology'):
                self.assertEqual(client.get(base + '/' + kind).status_code, 410)
                self.assertEqual(client.get(f'/scenes/{self.scene}/releases/missing/{kind}').status_code, 404)
            self.assertEqual(client.get(base).status_code, 200)

    def test_inspection_recomputes_rules_and_checks_original_bytes(self):
        from packages.service.query import SampleService
        original = SampleService(self.packages['a']).export_snapshot()
        from copy import deepcopy
        legacy = deepcopy(original)
        legacy['snapshot'].pop('inspection')
        for kind in ('data', 'ontology'):
            with self.assertRaises(QueryError) as caught:
                SampleService.from_snapshot(legacy).inspection(kind)
            self.assertEqual(caught.exception.code, 'inspection_unavailable')
        for key, kind in (('manifest_raw', 'data'), ('ontology_raw', 'ontology')):
            payload = deepcopy(original)
            payload['snapshot']['inspection'][key] += ' '
            with self.assertRaises(QueryError) as caught:
                SampleService.from_snapshot(payload).inspection(kind)
            self.assertEqual(caught.exception.code, 'content_corrupt')
        for field, replacement, location in [('type_id', 'missing-type', '/type_id'),
                                               ('properties', {}, '/properties/name')]:
            payload = deepcopy(original)
            payload['snapshot']['objects'][0][field] = replacement
            with self.assertRaisesRegex(QueryError, 'room-a.*' + location):
                SampleService.from_snapshot(payload).inspection('ontology')

    def test_concurrent_switch_single_winner_postgresql(self):
        if self.engine.dialect.name != 'postgresql':
            self.skipTest('PostgreSQL row-lock concurrency test requires isolated database')
        barrier = threading.Barrier(2)
        def switch(version):
            barrier.wait(timeout=5)
            try:
                return self.manager.activate(self.scene, version, 0, 'engineer')['release_id']
            except ReleaseError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(switch, ['a', 'b']))
        self.assertEqual(outcomes.count('revision_conflict'), 1)
        self.assertEqual(self.manager.current(self.scene)['revision'], 1)

    def test_query_serializes_after_revocation_commit_postgresql(self):
        if self.engine.dialect.name != 'postgresql':
            self.skipTest('PostgreSQL revocation serialization test requires isolated database')
        started = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.store.transaction(self.scene) as tx:
                tx.revoke('a', 'reviewer', 'committing revocation')
                def query():
                    started.set()
                    return self.query()
                future = pool.submit(query)
                self.assertTrue(started.wait(5))
            with self.assertRaises(QueryError):
                future.result(timeout=5)


if __name__ == '__main__':
    unittest.main()
