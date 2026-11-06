"""Local synthetic SQLite UI preview; not the PostgreSQL deployment entry point."""
import os
from pathlib import Path
import tempfile

import uvicorn
from sqlalchemy import create_engine

from apps.api.managed import create_managed_app
from packages.infrastructure.releases import ReleaseStore
from packages.lifecycle.releases import ReleaseManager
from packages.infrastructure.delivery_reports import ReportArchive
from packages.service.delivery import SavedDeliveryReader
from packages.infrastructure.files import LocalFiles
from packages.infrastructure.imports import ImportStore
from packages.infrastructure.jobs import JobStore
from packages.infrastructure.runner import LocalRunner
from packages.data.imports import ImportManager
from packages.construction.reading import JobReader


def main():
    with tempfile.TemporaryDirectory(prefix='cospace-preview-') as temporary:
        root = Path(temporary)
        url = 'sqlite:///' + (root / 'preview.db').as_posix()
        engine = create_engine(url)
        try:
            store = ReleaseStore(engine)
            store.initialize_demo()
            manager = ReleaseManager(store)
            manager.register(Path('examples/indoor-spatial'))
            manager.activate('synthetic-equipment-corridor', 'release-spatial-sample-001', 0, 'local-preview')
            from experiments.scripts.seed_jobview import main as seed_jobs
            os.environ['COSPACE_DATABASE_URL'] = url
            os.environ['COSPACE_DATA_ROOT'] = str(root / 'data')
            seed_jobs()
            files = LocalFiles(root / 'data')
            reader = JobReader(JobStore(engine), ImportManager(ImportStore(engine), files), LocalRunner(files))
            archive = Path('experiments/runs/p2-delivery-acceptance-002/reports')
            first = next(iter(sorted(archive.glob('*.json'))), None)
            app = create_managed_app(manager, workbench_dir=Path('apps/workbench/dist'), job_reader=reader,
                                     delivery_reader=SavedDeliveryReader(first) if first else None,
                                     delivery_archive=ReportArchive(archive))
            uvicorn.run(app, host='127.0.0.1', port=8766)
        finally:
            engine.dispose()


if __name__ == '__main__':
    main()
