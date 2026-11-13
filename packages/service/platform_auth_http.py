"""RP HTTP assembly; business resources are optional and require an access gate."""
from pathlib import Path
from contextlib import AsyncExitStack, asynccontextmanager
from urllib.parse import parse_qs, urlsplit
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from packages.service.static_assets import WorkbenchAssets
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from packages.infrastructure.platform_rp import APP_ROUTES
from packages.infrastructure.platform_identity import IdentityRejected, IdentityUnavailable
from packages.infrastructure.platform_subscription import SubscriptionUnavailable, WebhookRejected, WebhookConflict


def disabled_auth_routes(app):
    @app.get('/api/auth/config')
    def disabled_config(): return {'enabled': False, 'mode': 'engineering_preview', 'business_authorization': False}


def create_auth_app(rp, workbench=Path('apps/workbench/dist'), business=None, access=None, subscriptions=None, reconciler=None, usage_reporter=None):
    if (business is None) != (access is None):raise ValueError('business_and_access_must_be_assembled_together')
    if business is not None and rp.config.issuer.startswith('https://') and (subscriptions is None or access.subscriptions is not subscriptions):
        raise ValueError('production_subscription_gate_required')
    mode='authorized_workbench' if business else 'identity_pilot'
    @asynccontextmanager
    async def lifespan(app):
        async with AsyncExitStack() as stack:
            for worker in (reconciler,usage_reporter):
                if worker is not None:await stack.enter_async_context(worker.lifespan(app))
            yield
    app = FastAPI(title='CoSpace platform identity pilot', docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(rp.config.origin).hostname])
    cookie = rp.config.cookie_name; browser_cookie = cookie+'_oidc'
    def set_cookie(response, name, value, **kwargs):
        response.set_cookie(name, value, httponly=True, secure=rp.config.origin.startswith('https://'),
                            samesite='lax', path='/', **kwargs)
    def clear_cookie(response, name):
        response.delete_cookie(name, httponly=True, secure=rp.config.origin.startswith('https://'), samesite='lax', path='/')
    def session_id(request): return request.cookies.get(cookie)
    def require_origin(request):
        if request.headers.get('origin') != rp.config.origin: raise HTTPException(403, 'origin_not_allowed')
        if request.headers.get('sec-fetch-site') == 'cross-site': raise HTTPException(403, 'origin_not_allowed')

    @app.middleware('http')
    async def headers(request, call_next):
        embed = request.url.path == '/space' and request.query_params.get('embed') == 'globe'
        parent = request.query_params.get('parent_origin', rp.config.origin)
        if embed and (access is None or not access.globe.allowed_parent(parent, rp.config.origin)
                      or any(len(request.query_params.getlist(key)) > 1 for key in request.query_params)):
            return JSONResponse({'detail':'globe_embed_origin_denied'},status_code=403)
        try: response = await call_next(request)
        except (OSError, ValueError) as exc:
            # Storage/key failures must not turn into a signed-out response.
            response = JSONResponse({'detail': 'session_store_unavailable'}, status_code=503)
        # Chromium sends Origin:null for form navigation under no-referrer.
        # Callback material stays private; the app document must retain a same-origin
        # source so browser POSTs can pass the explicit Origin/CSRF checks.
        referrer = 'no-referrer' if request.url.path.startswith('/auth/') else 'same-origin'
        if not request.url.path.startswith('/assets/') or response.status_code not in (200, 206, 304):
            response.headers['Cache-Control'] = 'no-store'
        response.headers.update({'Referrer-Policy': referrer,
                                 'X-Content-Type-Options': 'nosniff'})
        if embed:
            response.headers['Content-Security-Policy'] = "frame-ancestors 'self' " + parent
        return response

    @app.exception_handler(IdentityRejected)
    async def rejected(request, exc):
        return JSONResponse({'detail': 'authentication_rejected'}, status_code=400)

    @app.exception_handler(IdentityUnavailable)
    async def unavailable(request, exc):
        return JSONResponse({'detail': 'platform_identity_unavailable'}, status_code=503)

    @app.exception_handler(SubscriptionUnavailable)
    async def subscription_unavailable(request, exc):
        return JSONResponse({'detail':'subscription_unavailable'},status_code=503)

    @app.get('/api/auth/config')
    def config():
        return {'enabled': True, 'mode': mode, 'business_authorization': business is not None,
                'subscription_authorization': subscriptions is not None}

    if subscriptions is not None:
        @app.get('/api/subscription')
        def subscription(request: Request):
            # Workspace comes exclusively from the verified RP token.
            if request.query_params:raise HTTPException(400,'subscription_context_from_session_only')
            session,_=rp.resolve(session_id(request),require_access=True)
            if session is None:raise HTTPException(401,'authentication_required')
            principal=rp.verifier.verify(session['access_token'])
            return subscriptions.summary(principal,session['access_token'])

        @app.post('/api/webhooks/vxture')
        async def webhook(request: Request):
            if request.query_params:raise HTTPException(400,'webhook_query_rejected')
            if request.headers.get('content-type','').split(';')[0]!='application/json':raise HTTPException(415,'json_required')
            raw=bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw)>65536:raise HTTPException(413,'webhook_budget')
            try:return await run_in_threadpool(subscriptions.webhook,bytes(raw),request.headers)
            except WebhookRejected:raise HTTPException(400,'webhook_rejected') from None
            except WebhookConflict:raise HTTPException(409,'webhook_id_payload_conflict') from None

    @app.get('/auth/login')
    def login(request: Request, returnTo: str = '/', selectAccount: bool = False, tenant_hint: str | None = None, workspace_hint: str | None = None):
        if any(len(request.query_params.getlist(k)) > 1 for k in ('tenant_hint', 'workspace_hint')):
            raise HTTPException(400, 'login_context_rejected')
        try: url, browser = rp.begin(returnTo, request.cookies.get(browser_cookie), select_account=selectAccount,
                                    tenant_hint=tenant_hint, workspace_hint=workspace_hint)
        except ValueError as exc: raise HTTPException(400, 'return_path_rejected') from exc
        response = RedirectResponse(url, status_code=302)
        set_cookie(response, browser_cookie, browser, max_age=600)
        return response

    @app.get('/auth/callback')
    def callback(request: Request):
        # Reject duplicate parameters; do not log/echo authorization code, state or error_description.
        query = request.query_params
        if any(len(query.getlist(k)) > 1 for k in ('state', 'code', 'error')):
            raise IdentityRejected('login_callback_rejected')
        rpsid, destination = rp.complete(query.get('state'), request.cookies.get(browser_cookie),
            code=query.get('code'), error=query.get('error'), old_session=session_id(request))
        response = RedirectResponse(rp.config.origin+destination, status_code=302)
        set_cookie(response, cookie, rpsid); clear_cookie(response, browser_cookie)
        return response

    def public_session(request, active=False):
        session, state = rp.resolve(session_id(request), active=active)
        payload = {'enabled': True, 'authenticated': session is not None, 'authority_state': state,
                   'mode': mode, 'business_authorization': business is not None}
        if session:
            principal = session['principal']
            payload.update(user={k: principal[k] for k in ('subject', 'org_id', 'workspace_id', 'display_name')},
                           csrf=session['csrf'], authority_ready=state in ('cached','confirmed')
                           and rp.now()<session['next_check_at'] and not session.get('retry_at',0), access_ready=session['access_expires_at'] > rp.now()
                           and not session.get('refresh_blocked') and not session.get('refresh_pending'))
            payload['user'].update(session.get('profile', {}))
        response = JSONResponse(payload)
        if not session and session_id(request): clear_cookie(response, cookie)
        return response

    @app.get('/api/auth/session')
    def session(request: Request): return public_session(request)

    @app.post('/api/auth/session')
    def activity(request: Request):
        require_origin(request)
        if not rp.csrf_matches(session_id(request), request.headers.get('x-cospace-csrf')):
            raise HTTPException(403, 'csrf_rejected')
        return public_session(request, active=True)

    @app.post('/auth/logout')
    async def logout(request: Request):
        require_origin(request)
        raw = await request.body()
        if len(raw) > 4096 or request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            raise HTTPException(400, 'logout_request_rejected')
        try: value = parse_qs(raw.decode(), strict_parsing=True)
        except (ValueError, UnicodeError) as exc: raise HTTPException(400, 'logout_request_rejected') from exc
        if set(value) != {'csrf'} or len(value['csrf']) != 1 or not rp.csrf_matches(session_id(request), value['csrf'][0]):
            raise HTTPException(403, 'csrf_rejected')
        url = await run_in_threadpool(rp.logout, session_id(request))
        response = RedirectResponse(url, status_code=303); clear_cookie(response, cookie)
        return response

    @app.post('/api/auth/logout')
    async def logout_api(request: Request):
        # Fetch POST retains Origin even when an ingress sets no-referrer on HTML.
        # Keep the same strict Origin and session CSRF checks as the form endpoint.
        require_origin(request)
        if not rp.csrf_matches(session_id(request), request.headers.get('x-cospace-csrf')):
            raise HTTPException(403, 'csrf_rejected')
        url = await run_in_threadpool(rp.logout, session_id(request))
        response = JSONResponse({'redirect_url': url}); clear_cookie(response, cookie)
        return response

    def app_entry():
        entry = Path(workbench) / 'index.html'
        if not entry.is_file(): raise HTTPException(404, 'workbench_not_built')
        return FileResponse(entry, media_type='text/html')

    for route in APP_ROUTES:
        app.add_api_route(route, app_entry, methods=['GET', 'HEAD'], include_in_schema=False)

    @app.api_route('/workbench/{retired:path}', methods=['GET', 'HEAD'])
    @app.api_route('/workbench', methods=['GET', 'HEAD'])
    @app.api_route('/index.html', methods=['GET', 'HEAD'])
    def retired_entry(): raise HTTPException(404, 'page_not_found')

    if business is None:
        @app.api_route('/api/{remaining:path}', methods=['GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'PATCH'])
        def business_closed(request: Request, remaining: str):
            session, state = rp.resolve(session_id(request))
            if session is None: raise HTTPException(401, 'authentication_required')
            raise HTTPException(503, 'space_authorization_not_configured')

    # Only generated assets are public; source/experimental HTML is never mounted.
    assets = Path(workbench) / 'assets'
    if assets.is_dir(): app.mount('/assets', WorkbenchAssets(directory=assets))
    if business is not None:
        app.mount('/',business)
        app.middleware('http')(access.dispatch)
    return app
