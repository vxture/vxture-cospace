"""Read-only, database-managed synthetic API. All queries check revocations."""
from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from apps.api.main import PointRequest
from packages.infrastructure.releases import ReleaseStore
from packages.lifecycle.releases import ReleaseError, ReleaseManager
from packages.service.query import QueryError
from packages.construction.errors import JobError
from packages.data.imports import ImportError
from packages.service.delivery import SavedDeliveryReader, DeliveryReportError
from packages.infrastructure.delivery_reports import ReportArchive


def create_managed_app(manager, close=None, workbench_dir=None, job_reader=None, delivery_reader=None, delivery_archive=None):
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if close:
                close()
    app = FastAPI(title='CoSpace managed synthetic releases', version='0.3.0', lifespan=lifespan)

    def archived(operation):
        headers = {'Cache-Control': 'no-store'}
        if delivery_archive is None:
            return JSONResponse({'detail': {'message': '尚未配置报告目录', 'code': 'delivery_archive_not_configured'}},
                                status_code=503, headers=headers)
        try:
            return JSONResponse(operation(), headers=headers)
        except DeliveryReportError as error:
            return JSONResponse({'detail': {'message': '报告目录不可读、超限或所选报告不符，请核对后重试', 'code': error.code}},
                                status_code=409 if error.code == 'delivery_report_target_mismatch' else 503, headers=headers)

    @app.get('/scenes/{scene_id}/releases/{release_id}/delivery-reports')
    def delivery_reports(scene_id: str, release_id: str):
        return archived(lambda: delivery_archive.list(scene_id, release_id))

    @app.get('/scenes/{scene_id}/releases/{release_id}/delivery-reports/{report_key}')
    def delivery_report(scene_id: str, release_id: str, report_key: str):
        return archived(lambda: delivery_archive.read(scene_id, release_id, report_key))

    @app.get('/scenes/{scene_id}/releases/{release_id}/delivery')
    def delivery(scene_id: str, release_id: str):
        headers = {'Cache-Control': 'no-store'}
        if delivery_reader is None:
            return JSONResponse({'detail': {'code': 'delivery_report_not_configured',
                'message': '尚未配置只读交付报告'}}, status_code=503, headers=headers)
        try:
            return JSONResponse(delivery_reader.read(scene_id, release_id), headers=headers)
        except DeliveryReportError as error:
            mismatch = error.code == 'delivery_report_target_mismatch'
            return JSONResponse({'detail': {'code': error.code, 'message':
                '报告与指定场景或发布不一致' if mismatch else '报告不可读、格式不符或超限，请重新生成并核对'}},
                status_code=409 if mismatch else 503, headers=headers)

    def call(operation):
        try:
            return operation()
        except (ReleaseError, QueryError, JobError, ImportError) as error:
            status = 404 if error.code in ('scene_not_found', 'release_not_found', 'no_current_release', 'job_not_found', 'dataset_not_found') else 409
            if error.code == 'capability_revoked':
                status = 410
            if error.code == 'content_corrupt':
                status = 503
            raise HTTPException(status, detail={'code': error.code, 'message': str(error)}) from error
        except SQLAlchemyError as error:
            raise HTTPException(503, detail={'code': 'storage_error', 'message': 'storage unavailable'}) from error
        except OSError as error:
            raise HTTPException(503, detail={'code': 'artifact_unavailable', 'message': 'fixed content unavailable'}) from error

    def jobs():
        if job_reader is None:
            raise HTTPException(503, detail={'code': 'job_reading_unavailable', 'message': 'job reading not configured'})
        return job_reader

    @app.get('/scenes/{scene_id}/jobs')
    def list_jobs(scene_id: str, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000)):
        return call(lambda: jobs().list(scene_id, limit, offset))

    @app.get('/scenes/{scene_id}/jobs/{job_id}')
    def job_detail(scene_id: str, job_id: str):
        return call(lambda: jobs().detail(scene_id, job_id))

    @app.get('/scenes/{scene_id}/jobs/{job_id}/input')
    def job_input(scene_id: str, job_id: str):
        return call(lambda: jobs().dataset(scene_id, job_id))

    @app.get('/scenes/{scene_id}/jobs/{job_id}/report')
    def job_report(scene_id: str, job_id: str):
        return call(lambda: jobs().report(scene_id, job_id))

    @app.get('/scenes/{scene_id}/current')
    def current(scene_id: str):
        return call(lambda: manager.current(scene_id))

    @app.get('/scenes/{scene_id}/releases/{release_id}')
    def trace(scene_id: str, release_id: str):
        return call(lambda: manager.trace(scene_id, release_id))

    @app.post('/query')
    def query(request: PointRequest):
        return call(lambda: manager.query(request.scene_id, request.release_id, request.frame_id, request.point))

    @app.get('/scenes/{scene_id}/releases/{release_id}/human')
    def human(scene_id: str, release_id: str):
        return call(lambda: manager.human(scene_id, release_id))

    @app.get('/scenes/{scene_id}/releases/{release_id}/data')
    def data(scene_id: str, release_id: str):
        return call(lambda: manager.inspection(scene_id, release_id, 'data'))

    @app.get('/scenes/{scene_id}/releases/{release_id}/ontology')
    def ontology(scene_id: str, release_id: str):
        return call(lambda: manager.inspection(scene_id, release_id, 'ontology'))

    if workbench_dir is not None:
        app.mount('/workbench', StaticFiles(directory=workbench_dir, html=True), name='workbench')

    return app


def managed_app():
    url = os.environ.get('COSPACE_DATABASE_URL')
    if not url:
        raise RuntimeError('COSPACE_DATABASE_URL required')
    engine = create_engine(url)
    if engine.dialect.name != 'postgresql':
        engine.dispose()
        raise RuntimeError('managed lifecycle requires PostgreSQL')
    dist = Path(__file__).resolve().parents[1] / 'workbench/dist'
    from packages.construction.reading import JobReader
    from packages.infrastructure.jobs import JobStore
    from packages.infrastructure.imports import ImportStore
    from packages.infrastructure.files import LocalFiles
    from packages.infrastructure.runner import LocalRunner
    from packages.data.imports import ImportManager
    root = os.environ.get('COSPACE_DATA_ROOT')
    reader = None
    if root:
        files = LocalFiles(root)
        reader = JobReader(JobStore(engine), ImportManager(ImportStore(engine), files), LocalRunner(files))
    report_path = os.environ.get('COSPACE_DELIVERY_REPORT')
    archive_path = os.environ.get('COSPACE_DELIVERY_ARCHIVE')
    return create_managed_app(ReleaseManager(ReleaseStore(engine)), engine.dispose,
                              dist if dist.is_dir() else None, reader,
                              SavedDeliveryReader(report_path) if report_path else None,
                              ReportArchive(archive_path) if archive_path else None)
