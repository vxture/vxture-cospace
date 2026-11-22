"""Authorized by the existing candidate/publication gate before these handlers."""
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse


def install(app, displays):
    def describe(kind, identity):
        try:
            result = displays.describe(kind, identity)
            # Integrity block tables are internal, not a second spatial directory.
            result['display'] = {k: v for k, v in result['display'].items() if k != 'files'}
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
                    info = displays.describe(kind, identity)['display']
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
