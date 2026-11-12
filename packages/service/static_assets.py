"""Cache and precompress only generated, public workbench assets."""
import mimetypes
import re
from starlette.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers


class WorkbenchAssets(StaticFiles):
    async def get_response(self, path, scope):
        response = None
        accepts = Headers(scope=scope).get('accept-encoding', '')
        gzip_ok = any(part.split(';')[0].strip().lower() == 'gzip'
                      and not re.search(r';\s*q=0(?:\.0*)?\s*$', part)
                      for part in accepts.split(','))
        if gzip_ok and path.endswith(('.js', '.css', '.json', '.svg')):
            try:
                response = await super().get_response(path + '.gz', scope)
                response.headers['Content-Encoding'] = 'gzip'
                response.headers['Content-Type'] = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        if response is None:
            response = await super().get_response(path, scope)
        response.headers['Vary'] = 'Accept-Encoding'
        if response.status_code in (200, 206, 304):
            # Vite filenames carry content hashes. Cesium's stable asset paths
            # must revalidate so a subsequent engine release cannot use old files.
            hashed = re.fullmatch(r'[^/]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+', path)
            response.headers['Cache-Control'] = ('public, max-age=31536000, immutable'
                                                  if hashed else 'public, max-age=0, must-revalidate')
        return response
