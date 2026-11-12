import gzip
from fastapi.testclient import TestClient
from test_platform_login import runtime
from packages.service.platform_auth_http import create_auth_app


def test_only_public_assets_are_cached_and_compressed(runtime, tmp_path):
    rp, *_ = runtime
    assets = tmp_path / 'assets'
    assets.mkdir()
    raw = b'export const globe = true;\n' * 200
    (assets / 'scene-globe-abcdefgh.js').write_bytes(raw)
    (assets / 'scene-globe-abcdefgh.js.gz').write_bytes(gzip.compress(raw))
    (assets / 'worker.js').write_bytes(raw)
    (tmp_path / 'index.html').write_text('<main>CoSpace</main>')
    with TestClient(create_auth_app(rp, tmp_path), base_url=rp.config.origin) as client:
        compressed = client.get('/assets/scene-globe-abcdefgh.js', headers={'Accept-Encoding': 'gzip'})
        assert compressed.content == raw
        assert compressed.headers['content-encoding'] == 'gzip'
        assert 'javascript' in compressed.headers['content-type']
        assert int(compressed.headers['content-length']) < len(raw) / 5
        assert compressed.headers['cache-control'] == 'public, max-age=31536000, immutable'
        assert compressed.headers['vary'] == 'Accept-Encoding'
        unchanged = client.get('/assets/scene-globe-abcdefgh.js', headers={
            'Accept-Encoding': 'gzip', 'If-None-Match': compressed.headers['etag']})
        assert unchanged.status_code == 304
        plain = client.get('/assets/scene-globe-abcdefgh.js', headers={'Accept-Encoding': 'gzip;q=0'})
        assert plain.content == raw and 'content-encoding' not in plain.headers
        fallback = client.get('/assets/worker.js', headers={'Accept-Encoding': 'gzip'})
        assert fallback.content == raw and 'content-encoding' not in fallback.headers
        assert fallback.headers['cache-control'] == 'public, max-age=0, must-revalidate'
        for path in ('/space', '/api/auth/config', '/api/auth/session', '/assets/missing.js', '/assets/%2e%2e/index.html'):
            assert client.get(path).headers['cache-control'] == 'no-store'
