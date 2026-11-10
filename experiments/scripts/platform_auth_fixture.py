"""LOCAL TEST IDP ONLY. Never wire into a real platform client or sample runtime."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from joserfc import jwt
from joserfc.jwk import RSAKey


class MockAccounts:
    def __init__(self, now=time.time, port=0):
        self.now = now; self.key = RSAKey.generate_key(2048, parameters={'kid': 'local-test-key'})
        self.client_id, self.secret, self.rp_origin = 'cospace-local-test', secrets.token_urlsafe(32), ''
        self.codes, self.pending, self.refreshes = {}, {}, {}
        self.calls = []; self.valid = True; self.unavailable = False; self.bad_nonce = False
        self.bad_subject = False; self.bad_sid = False; self.refresh_failure = False
        self.fail_after_consume = False; self.refresh_delay = 0; self.access_seconds = 120
        self.subject='usr_local_test';self.roles=['workspace:owner'];self.workspace='ws_mock'
        self.identity_options=None
        self.identity_roles={}
        self.profile_claims={}
        # Explicit test-only service clients; empty by default, no production fallback.
        self.service_clients={}
        parent = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass  # Access logs must not retain callback/token material.
            def send(self, status, value=None, location=None):
                if location and any(ord(char)<32 or ord(char)==127 for char in location):
                    return self.send(400, {'error':'invalid_redirect'})
                self.send_response(status)
                self.send_header('Cache-Control', 'no-store')
                if location: self.send_header('Location', quote(location, safe=":/?#[]@!$&'()*+,;=%"))
                self.send_header('Content-Type', 'application/json' if isinstance(value, dict) else 'text/html; charset=utf-8')
                self.end_headers()
                if value is not None: self.wfile.write((json.dumps(value) if isinstance(value, dict) else value).encode())
            def do_GET(self):
                path = urlsplit(self.path); q = {k:v[0] for k,v in parse_qs(path.query).items()}
                if path.path == '/oidc/jwks': return self.send(200, {'keys': [parent.key.as_dict(private=False)]})
                if path.path == '/oidc/authorize':
                    if (q.get('client_id') != parent.client_id or q.get('redirect_uri') != parent.rp_origin+'/auth/callback'
                            or q.get('code_challenge_method') != 'S256' or q.get('response_type') != 'code'):
                        return self.send(400, {'error': 'invalid_request'})
                    identity = secrets.token_urlsafe(32); parent.pending[identity] = q
                    links=('<a href="/test/approve?request='+identity+'">使用模拟身份继续</a>')
                    if parent.identity_options:
                        links=''.join('<p><a href="/test/approve?request='+identity+'&user='+subject+'">'+label+'</a></p>'
                            for subject,label in parent.identity_options.items())
                    return self.send(200, '<h1>本地模拟平台</h1><p>仅验证认证流程，不是真实平台登录。</p>'+links)
                if path.path == '/test/approve':
                    pending = parent.pending.pop(q.get('request'), None)
                    if not pending: return self.send(400, {'error': 'invalid_request'})
                    parent.valid = True
                    if parent.identity_options:
                        if q.get('user') not in parent.identity_options:return self.send(400,{'error':'invalid_mock_identity'})
                        pending['mock_subject']=q['user']
                    code = parent.issue(pending)
                    return self.send(302, location=pending['redirect_uri']+'?'+urlencode({'state':pending['state'], 'code':code}))
                if path.path == '/oidc/end_session':
                    if q.get('client_id') != parent.client_id or q.get('post_logout_redirect_uri') != parent.rp_origin+'/':
                        return self.send(400, {'error': 'invalid_request'})
                    parent.valid = False; parent.calls.append({'path':'/oidc/end_session'})
                    return self.send(302, location=q['post_logout_redirect_uri'])
                return self.send(404)
            def do_POST(self):
                path = urlsplit(self.path).path
                expected = 'Basic '+base64.b64encode((parent.client_id+':'+parent.secret).encode()).decode()
                if path=='/oidc/token' and self.headers.get('Authorization')!=expected:
                    length=int(self.headers.get('Content-Length',0))
                    if not 0<length<=8192:return self.send(400,{'error':'invalid_request'})
                    body={k:v[0] for k,v in parse_qs(self.rfile.read(length).decode()).items()}
                    for client_id,config in parent.service_clients.items():
                        auth='Basic '+base64.b64encode((client_id+':'+config['secret']).encode()).decode()
                        if self.headers.get('Authorization')!=auth:continue
                        expected_body={'grant_type':'urn:ietf:params:oauth:grant-type:token-exchange','audience':config['audience'],
                                       'org_id':config['org_id'],'workspace_id':config['workspace_id']}
                        if body!=expected_body:return self.send(403,{'error':'mock_exchange_denied'})
                        parent.calls.append({'path':path,'grant_type':body['grant_type'],'mock_service':True})
                        now=int(parent.now())
                        claims={'iss':parent.issuer,'aud':config['audience'],'act':{'sub':config['caller']},'mode':'service',
                            'scope':'tool:'+config['audience'],'org_id':config['org_id'],'workspace_id':config['workspace_id'],
                            'jti':secrets.token_urlsafe(16),'iat':now,'exp':now+300}
                        token=jwt.encode({'alg':'RS256','kid':parent.key.kid},claims,parent.key)
                        return self.send(200,{'access_token':token,'token_type':'Bearer','expires_in':300,
                            'issued_token_type':'urn:ietf:params:oauth:token-type:access_token'})
                    return self.send(401,{'error':'invalid_client'})
                if self.headers.get('Authorization') != expected: return self.send(401, {'error':'invalid_client'})
                raw = self.rfile.read(int(self.headers.get('Content-Length',0)))
                body = json.loads(raw) if path == '/oidc/session/status' else {k:v[0] for k,v in parse_qs(raw.decode()).items()}
                if path == '/oidc/session/status':
                    parent.calls.append({'path':path, 'active':body.get('active')})
                    if parent.unavailable: return self.send(503, {'error':'unavailable'})
                    return self.send(200, {'valid':True, 'next_check_at':int(parent.now())+90} if parent.valid else {'valid':False})
                if path != '/oidc/token': return self.send(404)
                parent.calls.append({'path':path, 'grant_type':body.get('grant_type')})
                if body.get('grant_type') == 'authorization_code':
                    value = parent.codes.pop(body.get('code'), None)
                    if not value: return self.send(400, {'error':'invalid_grant'})
                    challenge = base64.urlsafe_b64encode(hashlib.sha256(body.get('code_verifier','').encode()).digest()).rstrip(b'=').decode()
                    if challenge != value['code_challenge'] or body.get('redirect_uri') != parent.rp_origin+'/auth/callback':
                        return self.send(400, {'error':'invalid_grant'})
                    subject=value.get('mock_subject',parent.subject)
                    context={'subject':subject,'workspace':parent.workspace,'roles':parent.identity_roles.get(subject,parent.roles)}
                    return self.send(200, parent.tokens(value['nonce'],context))
                if body.get('grant_type') == 'refresh_token':
                    time.sleep(parent.refresh_delay)
                    token = body.get('refresh_token')
                    if parent.refresh_failure or token not in parent.refreshes: return self.send(400, {'error':'invalid_grant'})
                    context=parent.refreshes.pop(token)
                    if parent.fail_after_consume: return self.send(503, {'error':'lost_reply_simulated'})
                    return self.send(200, parent.tokens(None,context))
                return self.send(400, {'error':'unsupported_grant_type'})
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.issuer = 'http://127.0.0.1:'+str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self): self.thread.start(); return self
    def stop(self): self.server.shutdown(); self.server.server_close(); self.thread.join()

    def issue(self, pending):
        code = secrets.token_urlsafe(32); self.codes[code] = pending; return code

    def tokens(self, nonce, context=None):
        context=context or {'subject':self.subject,'workspace':self.workspace,'roles':self.roles}
        now = int(self.now()); sid = 'mock-central-session'
        base = {'iss':self.issuer,'aud':self.client_id,'sub':context['subject'],'iat':now,'exp':now+self.access_seconds,
                'sid':sid,'userType':'tenant_user'}
        access = base | {'active_org':'org_mock','active_workspace':context['workspace'],'account_status':'active',
                         'roles':context['roles'],'name':self.identity_options.get(context['subject'],'模拟用户') if self.identity_options else '模拟用户'}
        access.update(self.profile_claims)
        identity = base.copy()
        if nonce is not None: identity['nonce'] = 'wrong' if self.bad_nonce else nonce
        if self.bad_subject: identity['sub'] = 'usr_wrong'
        if self.bad_sid: identity['sid'] = 'wrong-sid'
        refresh = secrets.token_urlsafe(32); self.refreshes[refresh]=context
        return {'token_type':'Bearer','expires_in':self.access_seconds,'refresh_token':refresh,
            'access_token':jwt.encode({'alg':'RS256','kid':self.key.kid},access,self.key),
            'id_token':jwt.encode({'alg':'RS256','kid':self.key.kid},identity,self.key)}
