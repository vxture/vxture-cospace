"""Synthetic point semantics and fixed-snapshot API behavior."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.data.structure import StructureError, check_structure
from packages.service.query import QueryError, SampleService
from packages.service.sample import validate_package
from scripts.build_sample import build


class PointQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'bundle'

    def service(self, mutate=None):
        build(self.root, mutate, spatial=True)
        return SampleService(self.root)

    def query(self, service, point, **overrides):
        request = dict(scene_id='synthetic-equipment-corridor', release_id='release-spatial-sample-001',
                       frame_id='sample-local', point=point)
        return service.query(**(request | overrides))

    def test_states_reasons_and_boundaries(self):
        service = self.service()
        for point, state, reason in (
            ([1, 0, 1], 'observed_free', 'synthetic_observation'),
            ([5, 3, 1], 'occupied', 'synthetic_observation'),
            ([8, 4, 1], 'unknown', 'unobserved'),
            ([3.5, .5, .5], 'unknown', 'conflict'),
            ([10, 0, 1], 'out_of_scope', 'outside_target_scope'),
            ([0, -1, 0], 'observed_free', 'synthetic_observation'),
            ([4, 0, 1], 'unknown', 'unobserved'),
        ):
            with self.subTest(point=point):
                result = self.query(service, point)
                self.assertEqual((result['state'], result['reason']), (state, reason))
                self.assertFalse(result['real_release_ready'])
                if state in ('occupied', 'observed_free'):
                    self.assertTrue(result['evidence_ids'])

    def test_no_free_without_evidence(self):
        def mutate(name, doc):
            if name == 'coverage.json':
                doc['regions'][0]['evidence_ids'] = []
        build(self.root, mutate, spatial=True)
        with self.assertRaisesRegex(ValueError, 'requires synthetic observation'):
            SampleService(self.root)

    def test_unregistered_evidence(self):
        def mutate(name, doc):
            if name == 'coverage.json':
                doc['regions'][0]['evidence_ids'] = ['missing']
        build(self.root, mutate, spatial=True)
        with self.assertRaisesRegex(ValueError, 'evidence reference'):
            SampleService(self.root)

    def test_region_outside_scope(self):
        def mutate(name, doc):
            if name == 'coverage.json':
                doc['regions'][0]['bounds'][0][0] = -100
        build(self.root, mutate, spatial=True)
        with self.assertRaisesRegex(ValueError, 'outside target'):
            SampleService(self.root)

    def test_unknown_overlay_and_degraded_reason(self):
        def mutate(name, doc):
            if name == 'coverage.json':
                doc['regions'].append({'region_id': 'degraded', 'bounds': [[0, -1, 0], [2, 1, 2]],
                    'state': 'unknown', 'reason': 'degraded', 'evidence_ids': ['synthetic-rays']})
        service = self.service(mutate)
        result = self.query(service, [1, 0, 1])
        self.assertEqual((result['state'], result['reason']), ('unknown', 'degraded'))

    def test_frame_and_version_mismatch_are_errors(self):
        service = self.service()
        for overrides in ({'frame_id': 'map'}, {'release_id': 'latest'}, {'scene_id': 'other'}):
            with self.assertRaises(QueryError):
                self.query(service, [1, 0, 1], **overrides)

    def test_bad_point_is_error(self):
        service = self.service()
        for point in ([True, 0, 0], [float('nan'), 0, 0], [float('inf'), 0, 0], [1, 2]):
            with self.assertRaises(ValueError):
                self.query(service, point)

    def test_tampering_rejected_at_load_old_snapshot_stays_pinned(self):
        service = self.service()
        original = self.query(service, [1, 0, 1])
        (self.root / 'coverage.json').write_text('{}', encoding='utf-8')
        self.assertEqual(self.query(service, [1, 0, 1]), original)
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            SampleService(self.root)

    def test_v01_compatible_but_no_query_capability(self):
        build(self.root)
        self.assertTrue(validate_package(self.root)['passed'])
        with self.assertRaisesRegex(QueryError, 'no point-query'):
            SampleService(self.root)

    def test_api_valid_requests_errors_and_openapi(self):
        build(self.root, spatial=True)
        with TestClient(create_app(self.root)) as client:
            metadata = client.get('/sample').json()
            request = {key: metadata[key] for key in ('scene_id', 'release_id', 'frame_id')}
            request['point'] = [1.0, 0.0, 1.0]
            response = client.post('/sample/query', json=request)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['state'], 'observed_free')
            self.assertEqual(response.json()['package_sha256'], metadata['package_sha256'])
            bad = client.post('/sample/query', json=request | {'frame_id': 'wrong'})
            self.assertEqual(bad.status_code, 409)
            self.assertEqual(bad.json()['detail']['code'], 'frame_mismatch')
            for patch in ({'point': [True, 0, 0]}, {'point': [1, 2]}, {'extra': 1}, {'point': ['1', 0, 0]}):
                self.assertEqual(client.post('/sample/query', json=request | patch).status_code, 422)
            self.assertIn('/sample/query', client.get('/openapi.json').json()['paths'])

    def test_cli_same_result(self):
        service = self.service()
        result = subprocess.run([sys.executable, '-m', 'apps.cli.query_sample', str(self.root),
             '--scene', 'synthetic-equipment-corridor', '--release', 'release-spatial-sample-001',
             '--frame', 'sample-local', '--point', '5', '3', '1'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['state'], self.query(service, [5, 3, 1])['state'])

    def test_standard_engine_preserves_integer_literal_policy(self):
        value = {'path': 'x', 'bytes': 1.0, 'sha256': 'a' * 64, 'media_type': 'application/json'}
        with self.assertRaises(StructureError) as caught:
            check_structure(value, 'file', 'entry')
        self.assertEqual(caught.exception.path, '/bytes')


if __name__ == '__main__':
    unittest.main()
