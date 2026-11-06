"""Cross-process check execution and state/visibility invariants."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from packages.data.imports import ImportManager, sha
from packages.infrastructure.files import LocalFiles
from packages.infrastructure.imports import ImportStore
from packages.infrastructure.jobs import JobStore, JobError
from packages.infrastructure.migrations import migrate_database
from packages.infrastructure.runner import LocalRunner
from packages.construction.jobs import JobManager
from scripts.build_sample import build


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / 'source'
        build(source, spatial=True)
        self.engine = create_engine(os.environ.get('COSPACE_TEST_DATABASE_URL', 'sqlite:///' + str(self.root / 'jobs.db')))
        self.addCleanup(self.engine.dispose)
        migrate_database(self.engine)
        self.files = LocalFiles(self.root / 'store')
        self.inputs = ImportManager(ImportStore(self.engine), self.files)
        result = self.inputs.ingest(source, {'schema_version': 'cospace.import/0.1',
            'scene_id': 'synthetic-equipment-corridor', 'data_kind': 'synthetic', 'source_description': 'fixture',
            'purpose': 'synthetic_check', 'usage_conditions': 'not_assessed', 'idempotency_key': uuid.uuid4().hex,
            'expected_manifest_sha256': sha((source / 'package.json').read_bytes())}, 'engineer')
        self.dataset = result['dataset_id']
        self.store = JobStore(self.engine)
        self.runner = LocalRunner(self.files)
        self.manager = JobManager(self.store, self.inputs, self.runner)

    def submit(self):
        return self.manager.submit(self.dataset, 'engineer')

    def test_real_child_report_fixed_context_and_tamper(self):
        job = self.submit()
        done = self.manager.run(job['job_id'], 0)
        self.assertEqual(done['state'], 'succeeded')
        self.assertEqual([e['state'] for e in done['events']], ['queued', 'running', 'succeeded'])
        report = self.manager.report(job['job_id'])
        self.assertEqual(report['dataset_sha256'], job['spec']['dataset_sha256'])
        self.assertFalse(report['candidate_created'])
        self.assertFalse(report['truth_created'])
        self.assertIn('slam', report['not_executed'])
        with self.assertRaises(JobError): self.manager.run(job['job_id'], 0)
        with self.assertRaises(JobError): self.store.cancel(job['job_id'], done['revision'])
        artifact = done['attempts'][0]['artifact']
        (self.files.root / 'artifacts' / artifact['artifact_id'] / 'validation_report.json').write_text('{}')
        with self.assertRaises(JobError): self.manager.report(job['job_id'])

    def test_cancel_and_preflight_failure(self):
        cancelled = self.submit()
        self.assertEqual(self.store.cancel(cancelled['job_id'], 0)['state'], 'cancelled')
        with self.assertRaises(JobError): self.manager.run(cancelled['job_id'], 0)
        job = self.submit()
        with patch.object(self.runner, 'fingerprint', return_value={'changed': True}):
            done = self.manager.run(job['job_id'], 0)
        self.assertEqual(done['state'], 'failed')
        self.assertEqual(done['attempts'][0]['diagnostic']['code'], 'environment_mismatch')
        self.assertIsNone(done['attempts'][0]['artifact'])

    def test_real_child_timeout(self):
        # Exercise the actual fixed child at a deadline below its startup time.
        job = self.submit()
        record = self.inputs.dataset(self.dataset)
        spec = job['spec']
        spec['config']['timeout_seconds'] = .000001
        with self.assertRaises(JobError) as caught:
            self.runner.execute(job['job_id'], 'attempt-' + uuid.uuid4().hex, spec, record['manifest'])
        self.assertEqual(caught.exception.code, 'timeout')
        self.assertFalse((self.files.root / 'artifacts').exists())

    def test_real_pipe_limit_nonzero_and_invalid_output(self):
        import subprocess
        import sys
        # Substitute the OS process only in tests; production has a fixed module entry.
        original_popen = subprocess.Popen
        dataset = self.inputs.dataset(self.dataset)
        for script, code in [("print('x'*50000)", 'log_limit'),
                             ("raise SystemExit(7)", 'executor_failed'),
                             ("import pathlib,sys; pathlib.Path(sys.argv[1], 'validation_report.json').write_text('{}')", 'invalid_output')]:
            job = self.submit()
            job['spec']['config']['log_limit_bytes'] = 1024
            def process(command, **kwargs):
                return original_popen([sys.executable, '-c', script, command[-1]], **kwargs)
            with patch('packages.infrastructure.runner.subprocess.Popen', side_effect=process):
                with self.assertRaises((JobError, ValueError)) as caught:
                    self.runner.execute(job['job_id'], 'attempt-' + uuid.uuid4().hex, job['spec'], dataset['manifest'])
            self.assertEqual(getattr(caught.exception, 'code', None), code)

    def test_worker_does_not_change_current_release(self):
        from packages.infrastructure.releases import ReleaseStore
        from packages.lifecycle.releases import ReleaseManager
        source = self.root / 'release-source'
        scene = 'worker-pointer-' + uuid.uuid4().hex
        def mutate(name, doc):
            if 'scene_id' in doc: doc['scene_id'] = scene
            if 'source_truth' in doc: doc['source_truth'] = {**doc['source_truth'], 'scene_id': scene}
        build(source, mutate, spatial=True)
        releases = ReleaseManager(ReleaseStore(self.engine))
        registered = releases.register(source)
        releases.activate(scene, registered['release_id'], 0, 'engineer')
        before = releases.current(scene)
        job = self.submit()
        self.assertEqual(self.manager.run(job['job_id'], 0)['state'], 'succeeded')
        self.assertEqual(releases.current(scene), before)
        failed = self.submit()
        with patch.object(self.runner, 'execute', side_effect=JobError('injected', 'failure')):
            self.assertEqual(self.manager.run(failed['job_id'], 0)['state'], 'failed')
        self.assertEqual(releases.current(scene), before)

    def test_failure_record_and_seal_commit_failure(self):
        for code in ('executor_failed', 'invalid_output', 'log_limit'):
            job = self.submit()
            with patch.object(self.runner, 'execute', side_effect=JobError(code, 'injected')):
                done = self.manager.run(job['job_id'], 0)
            self.assertEqual(done['state'], 'failed')
            self.assertEqual(done['attempts'][0]['diagnostic']['code'], code)
        job = self.submit()
        with patch.object(self.store, 'finish', side_effect=SQLAlchemyError('injected')):
            with self.assertRaises(SQLAlchemyError): self.manager.run(job['job_id'], 0)
        self.assertEqual(self.store.get(job['job_id'])['state'], 'running')
        with self.assertRaises(JobError): self.manager.report(job['job_id'])
        self.assertEqual(len(list((self.files.root / 'artifacts').iterdir())), 1)

    def test_postgres_claim_competition(self):
        if self.engine.dialect.name != 'postgresql': self.skipTest('PostgreSQL concurrency requires isolated database')
        job = self.submit()
        barrier = threading.Barrier(2)
        def claim(_):
            barrier.wait(timeout=5)
            try: return self.store.claim(job['job_id'], 0)
            except JobError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(claim, range(2)))
        self.assertEqual(outcomes.count('state_conflict'), 1)
        self.assertEqual(len(self.store.get(job['job_id'])['attempts']), 1)

    def test_postgres_claim_cancel_competition(self):
        if self.engine.dialect.name != 'postgresql': self.skipTest('PostgreSQL concurrency requires isolated database')
        job = self.submit()
        barrier = threading.Barrier(2)
        def transition(action):
            barrier.wait(timeout=5)
            try:
                if action == 'claim': self.store.claim(job['job_id'], 0)
                else: self.store.cancel(job['job_id'], 0)
                return action
            except JobError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(transition, ['claim', 'cancel']))
        self.assertEqual(results.count('state_conflict'), 1)
        state = self.store.get(job['job_id'])
        self.assertIn(state['state'], ('running', 'cancelled'))
        self.assertEqual(len(state['attempts']), 1 if state['state'] == 'running' else 0)

    def test_postgres_cli_submit_run_report(self):
        if self.engine.dialect.name != 'postgresql': self.skipTest('CLI requires PostgreSQL')
        import json
        import subprocess
        import sys
        env = {**os.environ, 'COSPACE_DATABASE_URL': os.environ['COSPACE_TEST_DATABASE_URL'], 'PYTHONUTF8': '1'}
        def cli(*args):
            result = subprocess.run([sys.executable, '-m', 'apps.cli.jobs', '--root', str(self.files.root), *args],
                                    env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)
        job = cli('submit', '--dataset', self.dataset, '--actor', 'cli-engineer')
        done = cli('run', job['job_id'], '--revision', '0')
        self.assertEqual(done['state'], 'succeeded')
        self.assertEqual(cli('status', job['job_id'])['revision'], 2)
        self.assertFalse(cli('report', job['job_id'])['candidate_created'])

    def test_readonly_api_scoping_input_report_and_corruption(self):
        from fastapi.testclient import TestClient
        from apps.api.managed import create_managed_app
        from packages.construction.reading import JobReader
        reader = JobReader(self.store, self.inputs, self.runner)
        queued = self.submit()
        success = self.submit()
        self.manager.run(success['job_id'], 0)
        base = '/scenes/synthetic-equipment-corridor/jobs'
        with TestClient(create_managed_app(None, job_reader=reader)) as client:
            listing = client.get(base + '?limit=1').json()
            self.assertTrue(listing['has_more'])
            self.assertEqual(len(listing['items']), 1)
            self.assertNotEqual(listing['items'][0]['job_id'], client.get(base + '?limit=1&offset=1').json()['items'][0]['job_id'])
            self.assertEqual(client.get('/scenes/empty/jobs').json()['items'], [])
            self.assertEqual(client.get(base + '?limit=1000').status_code, 422)
            path = base + '/' + success['job_id']
            detail = client.get(path).json()
            self.assertEqual(detail['state'], 'succeeded')
            source = client.get(path + '/input').json()
            self.assertEqual(source['spec_sha256'], detail['sha256'])
            self.assertEqual(source['manifest']['dataset_id'], self.dataset)
            self.assertEqual(len(source['manifest']['members']), 8)
            report = client.get(path + '/report').json()
            self.assertFalse(report['report']['candidate_created'])
            self.assertNotIn(str(self.root), str(report))
            self.assertEqual(client.get(base + '/' + queued['job_id'] + '/report').status_code, 409)
            self.assertEqual(client.get('/scenes/wrong/jobs/' + success['job_id']).status_code, 404)
            self.assertEqual(client.get(base + '/missing').status_code, 404)
            for suffix in ('', '/run', '/cancel', '/submit'):
                self.assertIn(client.post(path + suffix).status_code, (404, 405))
            done = self.store.get(success['job_id'])
            artifact = done['attempts'][0]['artifact']
            (self.files.root / 'artifacts' / artifact['artifact_id'] / 'validation_report.json').write_text('{}')
            self.assertEqual(client.get(path + '/report').status_code, 503)
            (self.files.root / 'datasets' / self.dataset / 'objects.json').unlink()
            self.assertEqual(client.get(path + '/input').status_code, 503)
            self.assertEqual(client.get(path).status_code, 200)

    def test_api_unconfigured_and_failed_job_diagnostics(self):
        from fastapi.testclient import TestClient
        from apps.api.managed import create_managed_app
        from packages.construction.reading import JobReader
        with TestClient(create_managed_app(None)) as client:
            self.assertEqual(client.get('/scenes/demo/jobs').status_code, 503)
        job = self.submit()
        with patch.object(self.runner, 'execute', side_effect=JobError('timeout', 'injected')):
            self.manager.run(job['job_id'], 0)
        with TestClient(create_managed_app(None, job_reader=JobReader(self.store, self.inputs, self.runner))) as client:
            path = '/scenes/synthetic-equipment-corridor/jobs/' + job['job_id']
            detail = client.get(path).json()
            self.assertEqual(detail['attempts'][0]['diagnostic']['code'], 'timeout')
            self.assertEqual(client.get(path + '/report').status_code, 409)
