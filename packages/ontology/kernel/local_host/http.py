"""Loopback transport for the standalone ontology host."""
from http import HTTPStatus
import re
import sqlite3
from urllib.parse import parse_qsl
from wsgiref.simple_server import WSGIRequestHandler, make_server

from ..authoring import AuthoringError
from ..catalog import CatalogError, MAX_BYTES, canonical_bytes
from ..workbench import DefinitionWorkbench
from .authoring_sqlite import SQLiteAuthoringPort
from .group_configuration import GroupConfigurationError, GroupConfigurationStore
from .identity import strict_json
from .storage import FILENAME

DEFINITIONS = '/api/ontology-definitions'
DIRECTORY = '/api/ontology-directory'
GROUPS = '/api/ontology-configuration/groups'
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


def read_body(environ):
    if environ.get('HTTP_TRANSFER_ENCODING'):
        raise RequestError(400, 'transfer_encoding_unsupported')
    if environ.get('CONTENT_TYPE', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise RequestError(415, 'json_required')
    length = environ.get('CONTENT_LENGTH', '')
    if not re.fullmatch(r'[0-9]{1,10}', length):
        raise RequestError(411, 'length_required')
    size = int(length)
    if size > _MAX_BODY:
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


class Application:
    def __init__(self, root, authority, authenticate):
        self.authority = authority
        self.authenticate = authenticate
        self.port = SQLiteAuthoringPort(root, filename=FILENAME)
        self.groups = GroupConfigurationStore(root, filename=FILENAME)

    def dispatch(self, environ):
        if environ.get('HTTP_HOST') != self.authority or environ.get('HTTP_ORIGIN'):
            raise RequestError(403, 'local_request_required')
        method, path = environ['REQUEST_METHOD'], environ['PATH_INFO']
        if path not in (DEFINITIONS, DIRECTORY, GROUPS):
            raise RequestError(404, 'not_found')
        # An injected adapter maps authentication to a trusted Principal.
        # Query, body, cookies and user-supplied identity headers are never used.
        principal = self.authenticate(environ.get('HTTP_AUTHORIZATION', ''))
        if principal is None:
            raise RequestError(401, 'authentication_required')
        if method not in ('GET', 'HEAD', 'POST') or (path == DIRECTORY and method == 'POST'):
            raise RequestError(405, 'method_not_allowed')
        query = query_params(environ.get('QUERY_STRING', ''))
        if (method == 'POST' or path != DEFINITIONS) and query:
            raise RequestError(422, 'invalid_request')
        scope, actor = principal.scope, principal.actor
        if path == GROUPS:
            if principal.authorize(scope, actor, 'configure_groups') is not True:
                raise RequestError(403, 'forbidden')
            settings = (self.groups.change(scope, actor, read_body(environ)) if method == 'POST'
                        else self.groups.read(scope))
            return {**settings, 'can_manage': True}

        workbench = DefinitionWorkbench(self.port, scope, actor, authorize=principal.authorize)
        if path == DIRECTORY:
            return workbench.released_library()
        if method == 'POST':
            return workbench.change(read_body(environ))
        if set(query) == {'module_id'}:
            return workbench.read(query['module_id'])
        if set(query) == {'review_id'}:
            return workbench.review_definition(query['review_id'])
        if set(query) == {'module_id', 'version', 'sha256'}:
            return workbench.definition(query)
        raise RequestError(422, 'invalid_request')

    def __call__(self, environ, start_response):
        status, problem = 200, None
        try:
            payload = canonical_bytes(self.dispatch(environ))
        except RequestError as exc:
            status, problem = exc.status, exc.code
        except AuthoringError as exc:
            status = (403 if exc.code == 'forbidden' else 422 if exc.code.startswith('invalid_')
                      else 404 if exc.code.endswith('_not_found') else 503 if
                      exc.code.startswith('store_') or exc.code.endswith('_integrity') else 409)
            problem = exc.code
        except GroupConfigurationError as exc:
            problem = str(exc)
            status = (422 if problem == 'ontology_group_invalid_request' else
                      503 if problem == 'ontology_group_configuration_invalid' else 409)
        except (CatalogError, OSError, sqlite3.Error, KeyError, TypeError, ValueError, RecursionError):
            status, problem = 503, 'ontology_host_unavailable'
        if problem:
            payload = canonical_bytes({'detail': problem})
        headers = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store'),
                   ('X-Content-Type-Options', 'nosniff'), ('Content-Length', str(len(payload)))]
        if status == 401:
            headers.append(('WWW-Authenticate', 'Bearer'))
        if status == 405:
            headers.append(('Allow', 'GET, HEAD' if environ['PATH_INFO'] == DIRECTORY else 'GET, HEAD, POST'))
        start_response(f'{status} {HTTPStatus(status).phrase}', headers)
        return [b'' if environ['REQUEST_METHOD'] == 'HEAD' else payload]


class LocalHandler(WSGIRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, *_args):
        # Query, headers, tokens and identity never enter an access log.
        pass


def server(root, port, authenticate):
    """Return a local server; leave production TLS/identity to the future host."""
    service = make_server('127.0.0.1', port, None, handler_class=LocalHandler)
    service.set_app(Application(root, f'127.0.0.1:{service.server_port}', authenticate))
    return service
