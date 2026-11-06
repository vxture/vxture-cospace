"""Local synthetic demo only. No formal release, authentication or revocation."""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from packages.service.query import QueryError, SampleService


class PointRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    scene_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    frame_id: str = Field(min_length=1)
    point: list[float] = Field(min_length=3, max_length=3)


def create_app(root):
    service = SampleService(root)  # Fail closed before any query can be served.
    app = FastAPI(title='CoSpace synthetic point query', version='0.2.0')

    @app.get('/sample')
    def describe():
        return service.describe()

    @app.post('/sample/query')
    def query(request: PointRequest):
        try:
            return service.query(request.scene_id, request.release_id, request.frame_id, request.point)
        except QueryError as error:
            raise HTTPException(status_code=409, detail={'code': error.code, 'message': str(error)}) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail={'code': 'invalid_point', 'message': str(error)}) from error

    return app


def demo_app():
    default = Path(__file__).resolve().parents[2] / 'examples/indoor-spatial'
    return create_app(os.environ.get('COSPACE_SAMPLE_ROOT', default))
