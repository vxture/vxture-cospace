"""Loopback transport for the standalone ontology host."""
from http import HTTPStatus
import re
import sqlite3
from urllib.parse import parse_qsl
from wsgiref.simple_server import WSGIRequestHandler, make_server

from ..authoring import AuthoringError
from ..catalog import CatalogError, MAX_BYTES, canonical_bytes
from ..exchange import MAX_EXCHANGE_BYTES
from ..workbench import DefinitionWorkbench
from .authoring_sqlite import SQLiteAuthoringPort
from .group_configuration import GroupConfigurationError, GroupConfigurationStore
from .identity import PERMISSIONS, strict_json
from .static import POLICY, WorkbenchAssets
from .storage import FILENAME

DEFINITIONS = '/api/ontology-definitions'
DIRECTORY = '/api/ontology-directory'
GROUPS = '/api/ontology-configuration/groups'
EXCHANGE = '/api/ontology-exchange/definitions'
SESSION = '/api/ontology-session'
DRAFTS = '/api/ontology-drafts'
_READ_ONLY = (DIRECTORY, SESSION, DRAFTS)
_REFERENCE_FIELDS = {'module_id', 'version', 'sha256'}
_MAX_BODY = MAX_BYTES + 8192


class RequestError(ValueError):
    def __init__(self, status, code):
        self.status, self.code = status, code


def query_params(raw):
    try:
        if len(raw) > 1024:
            raise ValueError()
        items = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=3, errors='strict')
        result = dict(items)
        if len(result) != len(items) or any(not value for value in result.values()):
            raise ValueError()
        return result
    except ValueError:
        raise RequestError(422, 'invalid_request') from None


def read_body(environ, *, maximum=_MAX_BODY):
    if environ.get('HTTP_TRANSFER_ENCODING'):
        raise RequestError(400, 'transfer_encoding_unsupported')
    if environ.get('CONTENT_TYPE', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise RequestError(415, 'json_required')
    length = environ.get('CONTENT_LENGTH', '')
    if not re.fullmatch(r'[0-9]{1,10}', length):
        raise RequestError(411, 'length_required')
    size = int(length)
    if size > maximum:
        raise RequestError(413, 'size_budget')
    try:
        raw = environ['wsgi.input'].read(size)
    except (TimeoutError, OSError):
        raise RequestError(400, 'incomplete_request') from None
    try:
        if len(raw) != size:
            raise ValueError()
        return strict_json(raw)
    except (ValueError, RecursionError):
        raise RequestError(422, 'invalid_request') from None


def exchange_response(workbench, method, query, environ):
    if method != 'POST':
        if set(query) != _REFERENCE_FIELDS:
            raise RequestError(422, 'invalid_request')
        return workbench.export_release(query)
    body = read_body(environ, maximum=2 * MAX_EXCHANGE_BYTES + 4096)
    if type(body) is not dict:
        raise RequestError(422, 'invalid_request')
    action = body.get('action')
    native = 'package_json' in body
    fields = {'action', 'package_json' if native else 'package'}
    if action == 'import':
        fields |= {'request_id', 'expected_revision'}
    if action not in ('preflight', 'import') or set(body) != fields:
        raise RequestError(422, 'invalid_request')
    try:
        if native and type(body['package_json']) is not str:
            raise ValueError()
        raw = body['package_json'].encode('utf-8') if native else canonical_bytes(body['package'])
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise CatalogError('invalid_json', '/') from None
    if action == 'preflight':
        return workbench.preflight_import(raw)
    return workbench.import_draft(raw, request_id=body['request_id'], expected_revision=body['expected_revision'])


class Application:
    def __init__(self, root, authority, authenticate, *, assets=None):
        self.authority = authority
        self.authenticate = authenticate
        self.assets = assets
        self.port = SQLiteAuthoringPort(root, filename=FILENAME)
        self.groups = GroupConfigurationStore(root, filename=FILENAME)

    def dispatch(self, environ):
        method, path = environ['REQUEST_METHOD'], environ['PATH_INFO']
        if path not in (DEFINITIONS, DIRECTORY, GROUPS, EXCHANGE, SESSION, DRAFTS):
            raise RequestError(404, 'not_found')
        # An injected adapter maps authentication to a trusted Principal.
        # Query, body, cookies and user-supplied identity headers are never used.
        principal = self.authenticate(environ.get('HTTP_AUTHORIZATION', ''))
        if principal is None:
            raise RequestError(401, 'authentication_required')
        if method not in ('GET', 'HEAD', 'POST') or (path in _READ_ONLY and method == 'POST'):
            raise RequestError(405, 'method_not_allowed')
        query = query_params(environ.get('QUERY_STRING', ''))
        if (method == 'POST' or path not in (DEFINITIONS, EXCHANGE)) and query:
            raise RequestError(422, 'invalid_request')
        scope, actor = principal.scope, principal.actor
        if path == SESSION:
            return {'profile': 'vxture.ontology-session/0.1', 'scope': scope, 'actor': actor,
                    'permissions': sorted(p for p in PERMISSIONS if principal.authorize(scope, actor, p) is True)}
        if path == GROUPS:
            if principal.authorize(scope, actor, 'configure_groups') is not True:
                raise RequestError(403, 'forbidden')
            settings = (self.groups.change(scope, actor, read_body(environ)) if method == 'POST'
                        else self.groups.read(scope))
            return {**settings, 'can_manage': True}

        workbench = DefinitionWorkbench(self.port, scope, actor, authorize=principal.authorize)
        if path == DRAFTS:
            return workbench.draft_directory()
        if path == EXCHANGE:
            if method == 'POST' and not all(principal.authorize(scope, actor, permission) is True
                                            for permission in ('read', 'read_private', 'edit')):
                raise RequestError(403, 'forbidden')
            return exchange_response(workbench, method, query, environ)
        if path == DIRECTORY:
            return workbench.released_library()
        if method == 'POST':
            return workbench.change(read_body(environ))
        if set(query) == {'module_id'}:
            return workbench.read(query['module_id'])
        if set(query) == {'review_id'}:
            return workbench.review_definition(query['review_id'])
        if set(query) == _REFERENCE_FIELDS:
            return workbench.definition(query)
        raise RequestError(422, 'invalid_request')

    def __call__(self, environ, start_response):
        status, problem, path = 200, None, None
        content_type, cache = 'application/json', 'no-store'
        try:
            origin = environ.get('HTTP_ORIGIN')
            if (environ.get('HTTP_HOST') != self.authority
                    or origin and (not self.assets or origin != f'http://{self.authority}')
                    or environ.get('HTTP_SEC_FETCH_SITE') in ('cross-site', 'same-site') and
                    environ['PATH_INFO'].startswith('/api/')):
                raise RequestError(403, 'local_request_required')
            if self.assets and (environ['PATH_INFO'] == '/' or environ['PATH_INFO'].startswith('/assets/')):
                if environ['REQUEST_METHOD'] not in ('GET', 'HEAD'):
                    raise RequestError(405, 'method_not_allowed')
                resource = self.assets.read(environ['PATH_INFO'])
                if resource is None:
                    raise RequestError(404, 'not_found')
                payload, content_type, cache = resource
            else:
                payload = canonical_bytes(self.dispatch(environ))
        except RequestError as exc:
            status, problem = exc.status, exc.code
        except AuthoringError as exc:
            status = (403 if exc.code == 'forbidden' else 422 if exc.code.startswith('invalid_')
                      else 404 if exc.code.endswith('_not_found') else 503 if
                      exc.code.startswith('store_') or exc.code.endswith('_integrity') else 409)
            problem = exc.code
            if environ['PATH_INFO'] == EXCHANGE:
                path = exc.path
        except GroupConfigurationError as exc:
            problem = str(exc)
            status = (422 if problem == 'ontology_group_invalid_request' else
                      503 if problem == 'ontology_group_configuration_invalid' else 409)
        except CatalogError as exc:
            if environ['PATH_INFO'] == EXCHANGE:
                status, problem, path = (413 if exc.code == 'size_budget' else 422), exc.code, exc.path
            else:
                status, problem = 503, 'ontology_host_unavailable'
        except (OSError, sqlite3.Error, KeyError, TypeError, ValueError, RecursionError):
            status, problem = 503, 'ontology_host_unavailable'
        if problem:
            payload = canonical_bytes({'detail': problem, **({'path': path} if path is not None else {})})
        headers = [('Content-Type', content_type), ('Cache-Control', cache), ('Content-Security-Policy', POLICY),
                   ('Referrer-Policy', 'no-referrer'), ('Cross-Origin-Resource-Policy', 'same-origin'),
                   ('X-Content-Type-Options', 'nosniff'), ('Content-Length', str(len(payload)))]
        if status == 401:
            headers.append(('WWW-Authenticate', 'Bearer'))
        if status == 405:
            endpoint = environ['PATH_INFO']
            readonly = endpoint in _READ_ONLY or endpoint == '/' or endpoint.startswith('/assets/')
            headers.append(('Allow', 'GET, HEAD' if readonly else 'GET, HEAD, POST'))
        start_response(f'{status} {HTTPStatus(status).phrase}', headers)
        return [b'' if environ['REQUEST_METHOD'] == 'HEAD' else payload]


class LocalHandler(WSGIRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, *_args):
        # Query, headers, tokens and identity never enter an access log.
        pass


def server(root, port, authenticate, *, ui_dir=None):
    """Return a local server; leave production TLS/identity to the future host."""
    assets = WorkbenchAssets(ui_dir) if ui_dir else None
    service = make_server('127.0.0.1', port, None, handler_class=LocalHandler)
    service.set_app(Application(root, f'127.0.0.1:{service.server_port}', authenticate, assets=assets))
    return service
