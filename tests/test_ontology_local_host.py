"""Validation of standalone identity configuration and trusted SQLite snapshots."""
from hashlib import sha256
from io import BytesIO
import json
import secrets
import sqlite3

import pytest

from packages.ontology.kernel.local_host.identity import PROFILE, TokenIdentity
from packages.ontology.kernel.local_host.http import Application, DEFINITIONS, DRAFTS, EXCHANGE, SESSION
from packages.ontology.kernel.local_host.identity import Principal
from packages.ontology.kernel.local_host.static import WorkbenchAssets
from packages.ontology.kernel.local_host.storage import FILENAME, initialize, snapshot
from packages.ontology.kernel import builtin_catalog


def test_local_identity_rejects_conflicting_configs(tmp_path):
    path = tmp_path / 'identity.json'
    first, second = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    principal = {'scope': 'park-a', 'actor': 'operator',
                 'token_sha256': sha256(first.encode()).hexdigest(), 'permissions': ['configure_groups']}

    def load(principals):
        path.write_text(json.dumps({'profile': PROFILE, 'principals': principals}), encoding='utf-8')
        return TokenIdentity.load(path)

    adapter = load([principal])
    identity = adapter('Bearer ' + first)
    assert identity.authorize('park-a', 'operator', 'configure_groups')
    assert not identity.authorize('park-b', 'operator', 'configure_groups')
    assert not identity.authorize('park-a', 'operator', 'publish')
    assert adapter('Bearer ' + second) is None
    for conflict in ({**principal, 'scope': 'park-b'},
                     {**principal, 'token_sha256': sha256(second.encode()).hexdigest()},
                     {**principal, 'permissions': ['owner']}):
        with pytest.raises(ValueError, match='invalid_identity_config'):
            load([principal, conflict])
    path.write_text('{"profile":"unexpected","profile":null}', encoding='utf-8')
    with pytest.raises(ValueError, match='invalid_identity_config'):
        TokenIdentity.load(path)


def test_snapshot_and_startup_refuse_foreign_databases(tmp_path):
    source = tmp_path / 'foreign'
    source.mkdir()
    with sqlite3.connect(source / FILENAME) as database:
        database.execute('CREATE TABLE foreign_store (id INTEGER PRIMARY KEY)')
    saved = (source / FILENAME).read_bytes()
    with pytest.raises(ValueError, match='invalid_host_database'):
        initialize(source)
    with pytest.raises(ValueError, match='invalid_host_database'):
        snapshot(source, tmp_path / 'copy')
    assert not (tmp_path / 'copy').exists()
    assert saved == (source / FILENAME).read_bytes()


def test_browser_transport_serves_only_workbench_assets_and_requires_same_origin(tmp_path):
    dist = tmp_path / 'ui'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<h1>Workbench</h1>', encoding='utf-8')
    (dist / 'assets' / 'index-ab012345.js').write_text('export {};', encoding='utf-8')
    (dist / 'assets' / 'state.json').write_text('{"private":true}', encoding='utf-8')
    host = '127.0.0.1:8791'
    writer = Principal('park', 'author', frozenset({'read', 'read_private', 'edit'}))
    viewer = Principal('park', 'viewer', frozenset({'read'}))
    app = Application(tmp_path / 'state', host, {'author': writer, 'viewer': viewer}.get, assets=WorkbenchAssets(dist))

    def request(path, *, method='GET', origin=None, authority=host, identity='', body=None, query='', site='same-origin'):
        raw = json.dumps(body).encode() if body is not None else b''
        env = {'HTTP_HOST': authority, 'REQUEST_METHOD': method, 'PATH_INFO': path, 'QUERY_STRING': query,
               'HTTP_AUTHORIZATION': identity, 'HTTP_SEC_FETCH_SITE': site, 'CONTENT_TYPE': 'application/json',
               'CONTENT_LENGTH': str(len(raw)), 'wsgi.input': BytesIO(raw)}
        if origin:
            env['HTTP_ORIGIN'] = origin
        result = []
        payload = b''.join(app(env, lambda status, headers: result.extend([int(status.split()[0]), dict(headers)])))
        return *result, payload

    status, headers, html = request('/')
    assert status == 200 and html == b'<h1>Workbench</h1>' and headers['Cache-Control'] == 'no-store'
    assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
    assert request('/assets/index-ab012345.js')[1]['Cache-Control'].endswith('immutable')
    assert request('/assets/index-ab012345.js', method='HEAD')[2] == b''
    assert request('/assets/state.json')[0] == request('/assets/../index.html')[0] == 404
    assert request('/', authority='other.example')[0] == 403
    assert request(SESSION)[0] == 401
    assert request(SESSION, identity='author', site='cross-site')[0] == 403
    assert request(DRAFTS, identity='viewer')[0] == 403
    assert json.loads(request(SESSION, identity='author')[2])['permissions'] == ['edit', 'read', 'read_private']

    body = {'action': 'save', 'module_id': 'core', 'expected_revision': 0,
            'request_id': 'b' * 32, 'base_reference': None, 'bundle': builtin_catalog().export('core')}
    assert request(DEFINITIONS, method='POST', identity='author', origin='http://other.example', body=body)[0] == 403
    assert request(DEFINITIONS, method='POST', identity='author', origin=f'http://{host}', body=body)[0] == 200
    assert json.loads(request(DRAFTS, identity='author')[2])['drafts'][0]['revision'] == 1
    malformed = {'action': 'preflight', 'package_json': '{"profile":1,"profile":2}'}
    status, _, payload = request(EXCHANGE, method='POST', identity='author', origin=f'http://{host}', body=malformed)
    assert status == 422 and json.loads(payload)['detail'] == 'duplicate_key'
