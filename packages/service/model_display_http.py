"""Authorized by the existing candidate/publication gate before these handlers."""
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
import sqlite3


class SourceQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    manifest_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    source_sha256: str = Field(pattern='^[a-f0-9]{64}$')


class ExactQuery(SourceQuery):
    x: float | None = None
    y: float | None = None
    z: float | None = None
    radius_m: float | None = Field(default=None, ge=.001, le=1)
    point_index: int | None = Field(default=None, ge=0)


def install(app, displays):
    @app.get('/candidates/{identity}/api/exact-objects')
    def exact_objects(identity: str, request: Request):
        try:
            values = dict(request.query_params)
            if len(values) != len(request.query_params.multi_items()):
                raise ValueError('exact_query_invalid')
            query = SourceQuery.model_validate_strings(values, strict=True)
            result = displays.exact.objects('candidate', identity, query.manifest_sha256, query.source_sha256)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except ValueError as exc:
            invalid = str(exc) == 'exact_query_invalid' or hasattr(exc, 'errors')
            raise HTTPException(422 if invalid else 404 if str(exc) == 'semantic_objects_not_available' else 409,
                                'exact_query_invalid' if invalid else 'exact_objects_unavailable') from None
        except (OSError, LookupError, TypeError, AttributeError, sqlite3.Error):
            raise HTTPException(409, 'exact_objects_unavailable') from None

    @app.get('/candidates/{identity}/api/exact')
    def exact(identity: str, request: Request):
        try:
            values = dict(request.query_params)
            if len(values) != len(request.query_params.multi_items()):
                raise ValueError('exact_query_invalid')
            query = ExactQuery.model_validate_strings(values, strict=True)
            point = [query.x, query.y, query.z]
            if query.point_index is not None and any(v is not None for v in [*point, query.radius_m]):
                raise ValueError('exact_query_invalid')
            result = displays.exact.read('candidate', identity, query.manifest_sha256, query.source_sha256,
                                        point=point, radius_m=query.radius_m, point_index=query.point_index)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except ValueError as exc:
            raise HTTPException(422 if str(exc) == 'exact_query_invalid' or hasattr(exc, 'errors') else 409,
                                'exact_query_invalid' if str(exc) == 'exact_query_invalid' or hasattr(exc, 'errors')
                                else 'exact_source_unavailable') from None
        except (OSError, LookupError, TypeError, AttributeError, sqlite3.Error):
            raise HTTPException(409, 'exact_source_unavailable') from None

    def describe(kind, identity):
        try:
            result = displays.describe(kind, identity)
            # Integrity block tables are internal, not a second spatial directory.
            for view in ('display', 'agent_display'):
                if view in result:
                    result[view] = {k: v for k, v in result[view].items() if k != 'files'}
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except (ValueError, OSError, LookupError, TypeError, AttributeError):
            raise HTTPException(409, 'model_display_unavailable') from None

    def resource(kind, identity, key, name, request):
        try:
            raw, start, end, size, checksum = displays.resource(kind, identity, key, name, request.headers.get('range'))
        except ValueError as exc:
            if str(exc) == 'display_integrity_changed':
                raise HTTPException(502, 'display_block_unavailable') from None
            if str(exc) in ('display_range_invalid', 'display_range_required'):
                # Resolve the size only after the same ownership/version checks.
                try:
                    info = displays.resource_display(kind, identity, key)
                    size = info.get('files', {}).get(name, {}).get('bytes')
                except (ValueError, OSError, LookupError, TypeError, AttributeError):
                    size = None
                headers = {'Cache-Control': 'no-store'}
                if size is not None:
                    headers['Content-Range'] = f'bytes */{size}'
                return Response(status_code=416, headers=headers)
            raise HTTPException(409, 'model_display_unavailable') from None
        except OSError:
            raise HTTPException(502, 'display_block_unavailable') from None
        except (LookupError, TypeError, AttributeError):
            raise HTTPException(409, 'model_display_unavailable') from None
        headers = {'Cache-Control': 'no-store', 'Accept-Ranges': 'bytes', 'ETag': f'"{checksum}"',
                   'X-CoSpace-Content-SHA256': checksum, 'Content-Encoding': 'identity',
                   'Content-Length': str(len(raw))}
        ranged = bool(request.headers.get('range'))
        if ranged:
            headers['Content-Range'] = f'bytes {start}-{end}/{size}'
        return Response(b'' if request.method == 'HEAD' else raw, status_code=206 if ranged else 200, headers=headers,
                        media_type='application/json' if name == 'metadata.json' else 'application/octet-stream')

    @app.get('/candidates/{identity}/api/display')
    def candidate(identity: str):
        return describe('candidate', identity)

    @app.get('/publications/{identity}/api/display')
    def publication(identity: str):
        return describe('publication', identity)

    @app.api_route('/candidates/{identity}/display/{key}/{name}', methods=['GET', 'HEAD'])
    def candidate_file(identity: str, key: str, name: str, request: Request):
        return resource('candidate', identity, key, name, request)

    @app.api_route('/publications/{identity}/display/{key}/{name}', methods=['GET', 'HEAD'])
    def publication_file(identity: str, key: str, name: str, request: Request):
        return resource('publication', identity, key, name, request)
