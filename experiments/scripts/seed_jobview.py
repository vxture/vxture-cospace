"""Temporary demo fixture using real import/check execution, never production data."""
import os
from pathlib import Path
from sqlalchemy import create_engine
from packages.data.imports import ImportManager, sha
from packages.infrastructure.files import LocalFiles
from packages.infrastructure.imports import ImportStore
from packages.infrastructure.jobs import JobStore
from packages.infrastructure.runner import LocalRunner
from packages.construction.jobs import JobManager


def main():
    engine = create_engine(os.environ['COSPACE_DATABASE_URL'])
    try:
        files = LocalFiles(os.environ['COSPACE_DATA_ROOT'])
        inputs = ImportManager(ImportStore(engine), files)
        source = Path('examples/indoor-spatial')
        record = inputs.ingest(source, {'schema_version': 'cospace.import/0.1', 'scene_id': 'synthetic-equipment-corridor',
            'data_kind': 'synthetic', 'source_description': 'temporary job workbench demo', 'purpose': 'synthetic_check',
            'usage_conditions': 'not_assessed', 'idempotency_key': 'jobview-demo',
            'expected_manifest_sha256': sha((source / 'package.json').read_bytes())}, 'demo-engineer')
        store = JobStore(engine)
        runner = LocalRunner(files)
        manager = JobManager(store, inputs, runner)
        for _ in range(1):
            job = manager.submit(record['dataset_id'], 'demo-engineer')
            done = manager.run(job['job_id'], 0)
            if done['state'] != 'succeeded':
                raise RuntimeError('demo check failed')
        manager.submit(record['dataset_id'], 'demo-engineer')
        cancelled = manager.submit(record['dataset_id'], 'demo-engineer')
        store.cancel(cancelled['job_id'], 0)
        failed = manager.submit(record['dataset_id'], 'demo-engineer')
        attempt = store.claim(failed['job_id'], 0)
        store.finish(failed['job_id'], attempt, diagnostic={'stage': 'execution', 'code': 'demo_failure',
            'message': '人为注入演示失败，不代表实际超时', 'attempt_id': attempt})
        print('Seeded real success, queued, cancelled and explicitly injected demo failure')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
