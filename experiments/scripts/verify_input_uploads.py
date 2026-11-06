"""P9 real HTTP replay and process restart for already uploaded scene samples.

Uses an existing isolated acceptance runtime. Replays must reuse its exact input
IDs; no build, candidate selection or publication is performed by this script.
"""
import argparse
from http.cookiejar import CookieJar
import io
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
from urllib.request import Request, build_opener, ProxyHandler, HTTPCookieProcessor
import zipfile
from cryptography.fernet import Fernet
from experiments.scripts.platform_auth_fixture import MockAccounts
from experiments.scripts.verify_preview_workflow import inventory
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.service.space_access import SpaceAccessPolicy


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def verify(args):
    sample=args.sample.resolve(); output=args.output.resolve(); original=Path('var/nyu').resolve()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',args.port))
    if (sample.is_relative_to(original) or original.is_relative_to(sample)
            or output.is_relative_to(sample) or sample.is_relative_to(output) or output.exists()
            or output.is_relative_to(original) or original.is_relative_to(output)):
        raise ValueError('existing_isolated_sample_and_exclusive_auth_output_required')
    cases=json.loads(args.cases.read_bytes())
    initial=sample/'preview-builds'/cases[0]['candidate_id']/'output'
    if not initial.is_dir():raise ValueError('existing_successful_candidate_required')
    output.mkdir(parents=True); baseline=inventory(sample); save(output/'sample-before.json',baseline)
    original_before=inventory(Path('var/nyu')); checks=[]; trace=[]; csrf={}; process=log=None
    accounts=MockAccounts().start(); accounts.roles=['workspace:member']; accounts.access_seconds=3600
    accounts.rp_origin=f'http://127.0.0.1:{args.port}'
    accounts.identity_options={'usr_manager':'模拟场景管理员','usr_local_test':'模拟查看者'}
    directory=PreviewSpaces(sample/'preview-directory'); scenes=directory.list('space')
    policy=SpaceAccessPolicy.model_validate({
        'bindings':[{'issuer':accounts.issuer,'space_id':s['id'],'org_id':'org_mock','workspace_id':'ws_mock'} for s in scenes],
        'grants':[{'issuer':accounts.issuer,'subject':'usr_manager','space_id':s['id'],'role':'manager'} for s in scenes]
            +[{'issuer':accounts.issuer,'subject':'usr_local_test','space_id':cases[0]['space_id'],'role':'viewer'}]})
    policies=SpacePolicyStore(output/'auth')
    policies.replace(policy,expected_revision=0,actor='local_upload_verifier',reason='isolated upload replay')
    env=os.environ.copy();env.update(COSPACE_OIDC_ISSUER=accounts.issuer,COSPACE_OIDC_BACKCHANNEL=accounts.issuer,
        COSPACE_OIDC_CLIENT_ID=accounts.client_id,COSPACE_OIDC_CLIENT_SECRET=accounts.secret,
        COSPACE_ORIGIN=accounts.rp_origin,COSPACE_SESSION_KEY=Fernet.generate_key().decode(),COSPACE_OIDC_LOOPBACK_HTTP='1')

    def client():return build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    def http(c,path,data=None,status=200,content_type='application/json',with_csrf=True,raw=False):
        headers={}
        if data is not None:
            headers={'Content-Type':content_type,'Origin':accounts.rp_origin}
            if with_csrf:headers['X-CoSpace-CSRF']=csrf.get(c,'')
        try:
            with c.open(Request(path if path.startswith('http') else accounts.rp_origin+path,data=data,headers=headers),timeout=90) as response:
                code=response.status; body=response.read()
        except HTTPError as exc:code=exc.code;body=exc.read()
        trace.append({'path':path.split('?')[0],'method':'POST' if data is not None else 'GET','status':code})
        assert code==status,(path,code,body[:300])
        return body if raw else json.loads(body)
    def login(c,user,workspace='ws_mock'):
        accounts.workspace=workspace
        with c.open(accounts.rp_origin+'/auth/login',timeout=20) as response:html=response.read().decode();base=response.geturl()
        link=next(v for v in re.findall(r'href="([^"]+)"',html) if 'user='+user in v)
        http(c,urljoin(base,link),raw=True); session=http(c,'/api/auth/session');csrf[c]=session['csrf']
        check(session['user']['workspace_id']==workspace,'login_'+workspace+'_'+user)
    def stop():
        nonlocal process,log
        if process and process.poll() is None:process.terminate();process.wait(timeout=15)
        if log:log.close()
        process=log=None
    def start(index):
        nonlocal process,log
        log=(output/f'server-{index}.log').open('wb')
        process=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.serve_platform_workbench',
            '--runtime',str(output/'auth'),'--sample',str(sample),'--initial',str(initial),'--port',str(args.port)],
            env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('upload_verification_server_exited')
            try:http(client(),'/api/auth/config');return
            except URLError:time.sleep(.1)
        raise TimeoutError('upload_verification_server_timeout')
    try:
        start(1);manager,viewer,other=client(),client(),client()
        login(manager,'usr_manager');login(viewer,'usr_local_test');login(other,'usr_manager','ws_other')
        accounts.workspace='ws_mock'
        case=cases[0];url='/api/input-uploads?'+urlencode({'space_id':case['space_id'],'label':'P9 repeat keeps original label'})
        http(client(),url,b'bad',401,'application/zip');check(True,'unauthenticated_upload_denied')
        http(viewer,url,b'bad',403,'application/zip');check(True,'viewer_upload_denied')
        http(other,url,b'bad',403,'application/zip');check(True,'foreign_workspace_upload_denied')
        http(manager,url,b'bad',403,'application/zip',with_csrf=False);check(True,'missing_csrf_denied')
        http(manager,url,b'bad',415);check(True,'non_zip_content_type_denied')
        http(manager,url,b'',413,'application/zip');check(True,'empty_upload_denied')
        http(manager,url,b'bad',422,'application/zip');check(True,'malformed_zip_denied')
        bad=io.BytesIO()
        with zipfile.ZipFile(bad,'w') as archive:
            archive.writestr('input.json','{}');archive.writestr('../outside.txt','must not escape')
        result=http(manager,url,bad.getvalue(),422,'application/zip')
        check(result['detail']=='upload_unsafe_member','zip_traversal_denied')
        check(inventory(sample)==baseline,'rejected_uploads_leave_scene_records_and_content_unchanged')
        for round_number in (1,2):
            if round_number==2:stop();start(2)
            for index,case in enumerate(cases):
                url='/api/input-uploads?'+urlencode({'space_id':case['space_id'],'label':'P9 repeat keeps original label'})
                result=http(manager,url,Path(case['bundle']).read_bytes(),200,'application/zip')
                check(not result['created'] and result['input']['id']==case['input_id'],f'round_{round_number}_sample_{index}_exact_input_reused')
                check(result['upload']['sha256']==case['sha256'],f'round_{round_number}_sample_{index}_exact_package_digest')
                detail=http(manager,'/api/inputs/'+case['input_id'])
                check(detail['registration_ref']['package_sha256']==case['sha256'],f'round_{round_number}_sample_{index}_source_receipt_preserved')
                preview=http(manager,'/candidates/'+case['candidate_id']+'/api/preview')
                check(preview['source']['input_binding']['id']==case['input_id'] and
                    preview['human_view']['source_model_sha256']==preview['agent_view']['source_model_sha256'],
                    f'round_{round_number}_sample_{index}_existing_dual_views_readable')
        check(inventory(sample)==baseline,'successful_replay_and_actual_restart_do_not_modify_existing_scene_artifacts')
        check(inventory(Path('var/nyu'))==original_before,'original_engineering_runtime_unchanged')
        save(output/'acceptance.json',{'status':'passed','passed':len(checks),'checks':checks,'http_requests':len(trace),
            'trace':trace,'identity_provider':'local_mock_only','sample':str(sample),'cases':cases,
            'execution':'real_HTTP_and_RP_process_restart','quality':'unverified'})
        print(json.dumps({'status':'passed','passed':len(checks),'http_requests':len(trace),'origin':accounts.rp_origin}),flush=True)
        if args.stay_open:
            while process.poll() is None:time.sleep(.5)
    finally:stop();accounts.stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',type=Path,required=True);parser.add_argument('--port',type=int,default=8774)
    parser.add_argument('--stay-open',action='store_true');verify(parser.parse_args())
