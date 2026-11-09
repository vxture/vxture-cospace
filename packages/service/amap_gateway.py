"""Authenticated JS API configuration and bounded official AMap security proxy."""
import os
import re
from urllib.parse import urlencode
import httpx2 as httpx
from fastapi.responses import JSONResponse, Response


UPSTREAMS = {
    '/v4/map/styles': 'https://webapi.amap.com/v4/map/styles',
    '/v3/assistant/coordinate/convert': 'https://restapi.amap.com/v3/assistant/coordinate/convert',
}


class AmapGateway:
    def __init__(self, key='', security_code='', transport=None):
        self.key, self.security_code, self.transport = key, security_code, transport

    @classmethod
    def from_env(cls):
        key = os.environ.get('COSPACE_AMAP_WEB_KEY', '')
        code = os.environ.get('COSPACE_AMAP_SECURITY_JS_CODE', '')
        if any(value and not re.fullmatch(r'[a-fA-F0-9]{32}', value) for value in (key, code)):
            raise ValueError('amap_configuration_invalid')
        return cls(key, code)

    async def dispatch(self, request):
        def error(status, detail):
            return JSONResponse({'detail': detail}, status_code=status, headers={'Cache-Control': 'no-store'})
        if request.method != 'GET':
            return error(405, 'map_read_only')
        enabled = bool(self.key and self.security_code)
        if request.url.path == '/api/map/config':
            return JSONResponse({'enabled': enabled, 'provider': 'amap',
                **({'key': self.key, 'service_host': '/_AMapService'} if enabled else {})},
                headers={'Cache-Control': 'no-store'})
        if not enabled:
            return error(503, 'map_not_configured')
        path = request.url.path.removeprefix('/_AMapService')
        query = request.query_params
        if (path not in UPSTREAMS or request.headers.get('sec-fetch-site') == 'cross-site'
                or len(str(query)) > 8192 or len(query) > 32
                or any(len(query.getlist(k)) != 1 for k in query)
                or 'jscode' in query or query.get('key', self.key) != self.key):
            return error(403, 'map_request_rejected')
        params = dict(query) | {'key': self.key, 'jscode': self.security_code}
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=12, follow_redirects=False) as client:
                async with client.stream('GET', UPSTREAMS[path]+'?'+urlencode(params)) as upstream:
                    if upstream.status_code != 200:
                        return error(502, 'map_upstream_unavailable')
                    content = bytearray()
                    async for chunk in upstream.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 8*1024*1024:
                            return error(502, 'map_upstream_budget')
                    # Never forward cookies, redirects or upstream diagnostics containing credentials.
                    if self.security_code.encode() in content or self.key.encode() in content:
                        return error(502, 'map_upstream_rejected')
                    return Response(bytes(content), media_type=upstream.headers.get('content-type', 'application/json'),
                        headers={'Cache-Control': 'private, max-age=300', 'X-Content-Type-Options': 'nosniff'})
        except httpx.HTTPError:
            return error(502, 'map_upstream_unavailable')
