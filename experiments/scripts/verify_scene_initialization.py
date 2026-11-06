"""P5a: actual CLI bootstrap, separate processes, mock-platform HTTP isolation and restart."""
import argparse
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urljoin
from urllib.request import Request,build_opener,ProxyHandler,HTTPCookieProcessor
from cryptography.fernet import Fernet
from experiments.scripts.platform_auth_fixture import MockAccounts
from experiments.scripts.verify_preview_workflow import inventory
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.service.space_access import SpaceAccessPolicy


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verify(output):
    output=output.resolve();original=Path('var/nyu').resolve()
    if output.is_relative_to(original) or original.is_relative_to(output):raise ValueError('exclusive_verification_output_required')
    output.mkdir(parents=True,exist_ok=False);before=inventory(Path('var/nyu'));save(output/'original-before.json',before)
    sample=output/'runtime';auth=output/'auth';checks=[];receipts=[]
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    accounts=MockAccounts().start();accounts.rp_origin=f'http://127.0.0.1:{port}';accounts.roles=['workspace:member'];accounts.access_seconds=3600
    accounts.identity_options={'usr_manager':'模拟管理员','usr_local_test':'模拟查看者'}
    process=log=None
    env=os.environ.copy();env.update(COSPACE_OIDC_ISSUER=accounts.issuer,COSPACE_OIDC_BACKCHANNEL=accounts.issuer,
        COSPACE_OIDC_CLIENT_ID=accounts.client_id,COSPACE_OIDC_CLIENT_SECRET=accounts.secret,COSPACE_ORIGIN=accounts.rp_origin,
        COSPACE_SESSION_KEY=Fernet.generate_key().decode(),COSPACE_OIDC_LOOPBACK_HTTP='1')
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    def cli(request_path,command,expect=0,extra=()):
        result=subprocess.run([sys.executable,'-X','utf8','-m','experiments.scripts.initialize_scene','--runtime',str(sample),
            '--policy-root',str(auth),'--request',str(request_path),command,*extra],capture_output=True,timeout=60,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert result.returncode==expect,result.stderr.decode('utf-8',errors='replace')
        return json.loads(result.stdout) if expect==0 else result.stderr.decode('utf-8')
    def initialize(path):
        plan=cli(path,'plan');save(path.with_suffix('.plan.json'),plan)
        result=cli(path,'apply',extra=('--expected-revision',str(plan['policy_revision']),'--plan-sha256',plan['plan_sha256']))
        save(path.with_suffix('.receipt.json'),result);return result
    def client():return build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    csrf={};trace=[]
    def http(c,path,body=None,status=200,binary=False):
        headers={} if body is None else {'Content-Type':'application/json','Origin':accounts.rp_origin,'X-CoSpace-CSRF':csrf.get(c,'')}
        try:
            with c.open(Request(path if path.startswith('http') else accounts.rp_origin+path,
                    data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=30) as response:code=response.status;raw=response.read()
        except HTTPError as exc:code=exc.code;raw=exc.read()
        trace.append({'path':path.split('?')[0],'status':code,'method':'POST' if body is not None else 'GET'})
        assert code==status,(path,code,raw[:500])
        return raw if binary else json.loads(raw)
    def login(c,user,workspace):
        accounts.workspace=workspace
        with c.open(accounts.rp_origin+'/auth/login',timeout=20) as response:html=response.read().decode();base=response.geturl()
        link=next(v for v in re.findall(r'href="([^"]+)"',html) if 'user='+user in v)
        http(c,urljoin(base,link),binary=True);session=http(c,'/api/auth/session')
        check(session['user']['workspace_id']==workspace,'verified_session_'+workspace+'_'+user);csrf[c]=session['csrf']
    def stop():
        nonlocal process,log
        if process and process.poll() is None:process.terminate();process.wait(timeout=15)
        if log:log.close()
        process=log=None
    def start(index):
        nonlocal process,log
        log=(output/f'server-{index}.log').open('wb')
        process=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.serve_platform_workbench','--runtime',str(auth),
            '--sample',str(sample),'--initial',str(sample/'initial'),'--port',str(port)],env=env,stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('verification_server_exited')
            try:http(client(),'/api/auth/config');return
            except URLError:time.sleep(.1)
        raise TimeoutError('verification_server_start_timeout')
    try:
        for workspace,preset in [('ws_mock','nyu-office-0001a'),('ws_mock','os1-multi-1'),('ws_other','nyu-office-0001a')]:
            path=output/(workspace+'-'+preset+'.json')
            request={'scope':{'issuer':accounts.issuer,'org_id':'org_mock','workspace_id':workspace},'preset_id':preset,
                'manager_subjects':['usr_manager'],'actor':'p5a_trusted_local_operator','reason':'P5a sample scene initialization; LOCAL MOCK ONLY'}
            save(path,request);receipt=initialize(path);receipts.append(receipt)
            check(receipt['created'] and len(receipt['inputs'])==1,workspace+':'+preset+':real_cli_creates_one_scene_one_input')
            repeated=initialize(path)
            check(not repeated['created'] and repeated['space_id']==receipt['space_id'] and repeated['inputs']==receipt['inputs'],workspace+':'+preset+':fresh_cli_reuses_scene_and_input')
        a,b,foreign=receipts
        check(len({r['space_id'] for r in receipts})==3 and a['project_id']==b['project_id']!=foreign['project_id'],'one_workspace_two_physical_scenes_other_workspace_separate')
        # A lost process after registration leaves an unbound intent, then normal CLI resumes.
        interrupted=output/'ws_crash-office.json';request=json.loads((output/'ws_mock-nyu-office-0001a.json').read_bytes())
        request['scope']['workspace_id']='ws_crash';save(interrupted,request)
        code='''
import json,os,sys
from pathlib import Path
from packages.lifecycle.scene_initialization import SceneInitialization,InitializationRequest
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.data.preview_source_config import load_sources
from packages.data.preview_inputs import PreviewInputs
runtime,auth,request_path=sys.argv[1:]
sources,_=load_sources('deploy/config/preview-sources.json',Path.cwd())
service=SceneInitialization(runtime,SpacePolicyStore(auth),sources,json.loads(Path('configs/samples/scene-presets.json').read_bytes()))
request=InitializationRequest.model_validate_json(Path(request_path).read_bytes());plan=service.plan(request)
original=PreviewInputs.register
def interrupted(*a,**k):
 original(*a,**k);os._exit(23)
PreviewInputs.register=interrupted
service.apply(request,plan['policy_revision'],plan['plan_sha256'])
'''
        crashed=subprocess.run([sys.executable,'-X','utf8','-c',code,str(sample),str(auth),str(interrupted)],capture_output=True,timeout=60)
        check(crashed.returncode==23,'actual_bootstrap_process_exits_after_input_before_binding')
        plan=cli(interrupted,'plan');check(plan['state']=='directory_ready','incomplete_intent_visible_after_real_process_exit')
        policies=SpacePolicyStore(auth);_,policy=policies.load()
        check(not any(v.space_id==plan['space_id'] for v in policy.bindings),'partial_scene_not_bound_or_authorized')
        recovered=initialize(interrupted);check(recovered['created'] and len(recovered['inputs'])==1,'explicit_cli_resume_recovers_registered_input_once')
        # A second process never silently restores a revoked grant.
        revision,policy=policies.load();value=policy.model_dump();value['grants']=[g for g in value['grants'] if g['space_id']!=recovered['space_id']]
        policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=revision,actor='test_admin',reason='P5a revocation negative')
        rejected=cli(interrupted,'plan',expect=2);check('no_repair' in rejected,'completed_initializer_refuses_to_regrant_revoked_scene')
        # Existing workspace first scene becomes viewer-visible through an explicit separate policy change.
        revision,policy=policies.load();value=policy.model_dump();value['grants'].append({'issuer':accounts.issuer,'subject':'usr_local_test','space_id':a['space_id'],'role':'viewer'})
        policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=revision,actor='test_admin',reason='P5a explicit viewer fixture')
        check(not (sample/'preview-builds').exists(),'initialization_does_not_build_select_or_publish')
        shutil.copytree('var/nyu/office-0001a-flow-001',sample/'initial')
        start(1);manager,other,viewer,anonymous=client(),client(),client(),client()
        http(anonymous,'/api/spaces',status=401)
        login(manager,'usr_manager','ws_mock');login(other,'usr_manager','ws_other');login(viewer,'usr_local_test','ws_mock')
        check({v['id'] for v in http(manager,'/api/spaces')['spaces']}=={a['space_id'],b['space_id']},'authorized_http_lists_two_current_workspace_scenes')
        check([v['id'] for v in http(other,'/api/spaces')['spaces']]==[foreign['space_id']],'authorized_http_other_workspace_lists_only_own_scene')
        check([v['id'] for v in http(viewer,'/api/spaces')['spaces']]==[a['space_id']],'viewer_only_lists_explicitly_granted_scene')
        for c,record in [(manager,foreign),(other,a),(viewer,b)]:
            http(c,'/api/spaces/'+record['space_id'],status=403)
            http(c,'/api/inputs?space_id='+record['space_id'],status=403)
            http(c,'/api/inputs/'+record['inputs'][0]['id'],status=403)
        check(True,'cross_workspace_and_ungranted_scene_direct_urls_denied')
        for record in (a,b):
            registered=http(manager,'/api/inputs?space_id='+record['space_id'])['inputs']
            check(len(registered)==1 and registered[0]['id']==record['inputs'][0]['id'],'scene_specific_input_'+record['preset_id'])
        for c in (manager,viewer):
            http(c,'/api/spaces',{'name':'Unapproved creation','project_id':a['project_id']},403)
            http(c,'/api/scene-initializations',{'preset_id':'nyu-office-0001a','workspace_id':'ws_other'},403)
        check(True,'scene_manager_and_viewer_do_not_gain_workspace_creation_authority')
        checked=http(manager,'/api/inputs/'+a['inputs'][0]['id']+'/preflight',{})
        check(checked['status']=='passed','initialized_data_enters_existing_preflight_flow')
        stop();start(2)
        # Existing signed sessions, policy, source settings and inputs survive RP restart.
        check(len(http(manager,'/api/spaces')['spaces'])==2,'scene_binding_survives_actual_rp_restart')
        check(http(manager,'/api/inputs/'+a['inputs'][0]['id']+'/preflight')['last_check']['status']=='passed','saved_preflight_survives_actual_restart')
        check(http(manager,'/api/source-settings?space_id='+b['space_id'])['sources'][0]['id']=='os1-single-frame','source_choice_survives_restart')
        check(inventory(Path('var/nyu'))==before,'original_195_engineering_files_unchanged')
        report={'profile':'cospace.scene-initialization-acceptance/0.1','status':'passed','passed':len(checks),'checks':checks,
            'runtime':str(sample),'policy_root':str(auth),'space_id':a['space_id'],'candidate_id':None,'publication_id':None,
            'scenes':receipts,'interrupted_recovery':recovered,'identity_provider':'local_mock_only',
            'scope':'trusted_local_initialization_and_authorized_resource_reads_not_platform_creation_api',
            'quality':'unverified','production_ready':False,'robot_ready':False,'original_records_unchanged':len(before)}
        save(output/'http-trace.json',trace);save(output/'acceptance.json',report)
        print(json.dumps(report,ensure_ascii=False))
    finally:stop();accounts.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();verify(args.output)
