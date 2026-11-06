"""Local HTTP RP/IdP integration, service restart and logout. No real platform calls."""
import argparse
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler
from cryptography.fernet import Fernet
from experiments.scripts.platform_auth_fixture import MockAccounts


def verify(output):
    output=output.resolve(); samples=Path('var/nyu').resolve()
    if output.exists() or output.is_relative_to(samples) or samples.is_relative_to(output):
        raise ValueError('new_separate_validation_output_required')
    original=json.loads(Path('experiments/evidence/2026-11-03/preview-lifecycle-h3c-001/original-before.json').read_bytes())
    def unchanged(): return all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in original.items())
    if not unchanged(): raise ValueError('historical_sample_changed_before_start')
    output.mkdir(parents=True); accounts=MockAccounts().start()
    with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    origin='http://127.0.0.1:'+str(port); accounts.rp_origin=origin
    env=os.environ.copy();env.update(COSPACE_OIDC_ISSUER=accounts.issuer,COSPACE_OIDC_BACKCHANNEL=accounts.issuer,
        COSPACE_OIDC_CLIENT_ID=accounts.client_id,COSPACE_OIDC_CLIENT_SECRET=accounts.secret,COSPACE_ORIGIN=origin,
        COSPACE_SESSION_KEY=Fernet.generate_key().decode(),COSPACE_OIDC_LOOPBACK_HTTP='1')
    cookies=CookieJar();opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(cookies))
    checks=[];trace=[];process=None;log=None;server_number=0
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value: raise AssertionError(name)
    def request(path,body=None,headers=None):
        method='POST' if body is not None else 'GET'
        url=path if path.startswith('http') else origin+path
        try: response=opener.open(Request(url,data=body,headers=headers or {}),timeout=8)
        except HTTPError as error:response=error
        with response:
            raw=response.read();status=response.status
        # Redact query strings/headers/bodies. Never archive code, cookies, CSRF or JWTs.
        from urllib.parse import urlsplit
        trace.append({'method':method,'path':urlsplit(url).path,'status':status})
        return status,raw
    def stop():
        nonlocal process,log
        if process and process.poll() is None:process.terminate();process.wait(timeout=10)
        if log:log.close()
        process=log=None
    def start():
        nonlocal process,log,server_number
        server_number+=1;log=(output/f'server-{server_number}.log').open('wb')
        process=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.serve_platform_auth',
            '--runtime',str(output/'sessions'),'--port',str(port)],env=env,stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if process.poll() is not None: raise RuntimeError('pilot_service_start_failed')
            try:
                with opener.open(origin+'/api/auth/config',timeout=.5) as response:
                    if response.status==200:return
            except (OSError,URLError):time.sleep(.1)
        raise RuntimeError('pilot_service_start_timeout')
    try:
        start()
        check('login_page_served',request('/workbench/layout.html')[0]==200)
        check('unauthenticated_business_denied',request('/api/spaces')[0]==401)
        status,html=request('/auth/login')
        check('top_level_redirect_reached_mock_accounts',status==200 and '本地模拟平台' in html.decode())
        approval=re.search(r'href="([^"]+)"',html.decode()).group(1)
        check('pkce_callback_returns_to_workbench',request(urljoin(accounts.issuer,approval))[0]==200)
        status,raw=request('/api/auth/session');data=json.loads(raw)
        check('verified_identity_visible',data['authenticated'] and data['user']['subject']=='usr_local_test')
        check('session_response_contains_no_tokens',not any(k in raw.decode() for k in ('access_token','id_token','refresh_token','client_secret','eyJ')))
        check('opaque_httponly_cookie',any(c.name=='cospace_rp' and len(c.value)==43 and c.has_nonstandard_attr('HttpOnly') for c in cookies))
        check('authenticated_business_stays_closed',request('/api/spaces')[0]==503)
        check('no_direct_publication_bypass',request('/publications/preview-1234567890123456/')[0]==404)
        check('no_root_model_bypass',request('/spatial.npz')[0]==404)
        before=sum(c['path']=='/oidc/session/status' for c in accounts.calls)
        for _ in range(3):request('/api/auth/session')
        check('background_poll_does_not_refresh_central_activity',sum(c['path']=='/oidc/session/status' for c in accounts.calls)==before)
        stop();start()
        status,raw=request('/api/auth/session');data=json.loads(raw)
        check('real_service_restart_retains_session',status==200 and data['authenticated'])
        check('cross_origin_activity_denied',request('/api/auth/session',b'',{'Origin':'https://other.example','X-CoSpace-CSRF':data['csrf']})[0]==403)
        check('csrf_logout_denied',request('/auth/logout',urlencode({'csrf':'invalid'}).encode(),{'Origin':origin,'Content-Type':'application/x-www-form-urlencoded'})[0]==403)
        check('global_logout_returns_to_login',request('/auth/logout',urlencode({'csrf':data['csrf']}).encode(),{'Origin':origin,'Content-Type':'application/x-www-form-urlencoded'})[0]==200)
        check('accounts_end_session_invoked',accounts.valid is False and accounts.calls[-1]['path']=='/oidc/end_session')
        check('local_session_removed',json.loads(request('/api/auth/session')[1])['authenticated'] is False)
        check('original_195_files_unchanged',unchanged())
        report={'profile':'cospace.platform-rp-i2-validation/0.1','checked_at':datetime.now(timezone.utc).isoformat(),
            'identity_provider':'local_mock_only','external_platform_calls':0,'service_processes':server_number,
            'service_restarts':server_number-1,'historical_files_checked':len(original),'http_requests':len(trace),
            'checks':checks,'business_http_acl_implemented':False,'real_platform_integration_verified':False}
        (output/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (output/'http-trace-redacted.json').write_text(json.dumps(trace,indent=2)+'\n',encoding='utf-8')
        return report
    finally:
        stop();accounts.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=verify(a.output)
    print(json.dumps({'passed':len(report['checks']),'http_requests':report['http_requests'],
        'service_restarts':report['service_restarts'],'historical_files_checked':report['historical_files_checked'],
        'real_platform_integration_verified':False}))


if __name__=='__main__':main()
