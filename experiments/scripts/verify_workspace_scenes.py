"""P5b real OIDC mock / HTTP / scene creation / source allocation / build replay.

--stay-open retains the isolated demo for browser acceptance, never changes 8770.
"""
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
from packages.data.preview_source_config import load_sources
from packages.data.space_sources import SpaceSources
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.service.space_access import SpaceAccessPolicy


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verify(args):
    output=args.output.resolve();source=args.sample.resolve();original=Path('var/nyu').resolve()
    if output.is_relative_to(original) or original.is_relative_to(output) or source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError('independent_verification_runtime_required')
    output.mkdir(parents=True,exist_ok=False)
    baseline=inventory(Path('var/nyu'));source_before=inventory(args.sample)
    save(output/'original-before.json',baseline);save(output/'source-before.json',source_before)
    sample=output/'runtime';sample.mkdir();auth=output/'auth';checks=[];trace=[]
    for folder in source.glob('preview-*'):
        if folder.is_dir():shutil.copytree(folder,sample/folder.name)
    initial=sample/'preview-builds'/args.candidate/'output'
    if not initial.is_dir():raise ValueError('existing_initial_candidate_required')
    port=args.port
    if not port:
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    accounts=MockAccounts().start();accounts.rp_origin=f'http://127.0.0.1:{port}'
    accounts.access_seconds=3600;accounts.roles=['workspace:member']
    accounts.identity_options={'usr_manager':'模拟场景管理员','usr_local_test':'模拟查看者','usr_owner':'模拟 Workspace Owner'}
    directory=PreviewSpaces(sample/'preview-directory');scenes=directory.list('space')
    policy=SpaceAccessPolicy.model_validate({'bindings':[
        {'issuer':accounts.issuer,'org_id':'org_mock','workspace_id':'ws_mock','space_id':s['id']} for s in scenes],
        'grants':[{'issuer':accounts.issuer,'space_id':s['id'],'subject':'usr_manager','role':'manager'} for s in scenes]
        +[{'issuer':accounts.issuer,'space_id':scenes[0]['id'],'subject':'usr_local_test','role':'viewer'}]})
    policies=SpacePolicyStore(auth);policies.replace(policy,expected_revision=0,actor='local_mock_verifier',reason='isolated P5b replay')
    sources,_=load_sources('deploy/config/preview-sources.json',Path.cwd());catalog=SpaceSources(directory.root,sources)
    config={'profile':'cospace.workspace-scenes/0.1','revision':1,'workspaces':[
        {'issuer':accounts.issuer,'org_id':'org_mock','workspace_id':ws,'allow_create':True,
         'creator_subjects':['usr_manager'],'source_bindings':{k:catalog.fingerprints[k] for k in keys}}
        for ws,keys in [('ws_mock',['nyu-office-short','os1-single-frame']),('ws_other',['os1-single-frame'])]]}
    config_path=auth/'workspace-scenes.json';save(config_path,config)
    env=os.environ.copy();env.update(COSPACE_OIDC_ISSUER=accounts.issuer,COSPACE_OIDC_BACKCHANNEL=accounts.issuer,
        COSPACE_OIDC_CLIENT_ID=accounts.client_id,COSPACE_OIDC_CLIENT_SECRET=accounts.secret,COSPACE_ORIGIN=accounts.rp_origin,
        COSPACE_SESSION_KEY=Fernet.generate_key().decode(),COSPACE_OIDC_LOOPBACK_HTTP='1')
    process=log=None;csrf={}
    def client():return build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    def http(c,path,body=None,status=200,binary=False,with_csrf=True):
        headers={} if body is None else {'Content-Type':'application/json','Origin':accounts.rp_origin}
        if body is not None and with_csrf:headers['X-CoSpace-CSRF']=csrf.get(c,'')
        try:
            with c.open(Request(path if path.startswith('http') else accounts.rp_origin+path,
                    data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=40) as r:
                code=r.status;raw=r.read()
        except HTTPError as exc:code=exc.code;raw=exc.read()
        trace.append({'path':path.split('?')[0],'status':code,'method':'POST' if body is not None else 'GET'})
        assert code==status,(path,code,raw[:500])
        return raw if binary else json.loads(raw)
    def login(c,user,workspace,roles=None):
        accounts.workspace=workspace;accounts.roles=roles or ['workspace:member']
        with c.open(accounts.rp_origin+'/auth/login',timeout=20) as r:html=r.read().decode();base=r.geturl()
        link=next(v for v in re.findall(r'href="([^"]+)"',html) if 'user='+user in v)
        http(c,urljoin(base,link),binary=True);session=http(c,'/api/auth/session');csrf[c]=session['csrf']
        check(session['user']['workspace_id']==workspace,'verified_session_'+workspace+'_'+user)
    def stop():
        nonlocal process,log
        if process and process.poll() is None:process.terminate();process.wait(timeout=15)
        if log:log.close()
        process=log=None
    def start(index):
        nonlocal process,log
        log=(output/f'server-{index}.log').open('wb')
        process=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.serve_platform_workbench',
            '--runtime',str(auth),'--sample',str(sample),'--initial',str(initial),'--port',str(port),
            '--workspace-scenes-config',str(config_path)],env=env,stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('verification_server_exited')
            try:http(client(),'/api/auth/config');return
            except URLError:time.sleep(.1)
        raise TimeoutError('server_start_timeout')
    try:
        start(1);manager,viewer,other,owner=client(),client(),client(),client()
        http(client(),'/api/workspace-scenes',status=401)
        login(manager,'usr_manager','ws_mock');login(viewer,'usr_local_test','ws_mock');login(other,'usr_manager','ws_other')
        ctx=http(manager,'/api/workspace-scenes');body={'name':'P5b · 新建办公室场景','description':'公开样本流程验证，精度未验收',
            'request_id':'a'*32,'context_sha256':ctx['context_sha256']}
        http(manager,'/api/workspace-scenes',body,403,with_csrf=False);check(True,'missing_csrf_denied')
        http(viewer,'/api/workspace-scenes',body,403);check(True,'viewer_cannot_create')
        for extra in ({'workspace_id':'ws_other'},{'project_id':scenes[0]['project_id']},{'scope':{}}):
            http(manager,'/api/workspace-scenes',body|extra,422)
        check(True,'browser_cannot_declare_tenant_or_parent_project')
        created=http(manager,'/api/workspace-scenes',body,201);space=created['space_id']
        check(created['workspace_id']=='ws_mock' and created['actor']=='usr_manager','creation_receipt_uses_verified_principal')
        check(http(manager,'/api/inputs?space_id='+space)['inputs']==[] and http(manager,'/api/builds?space_id='+space)['jobs']==[],
              'new_scene_starts_empty_no_automatic_build')
        replay=http(manager,'/api/workspace-scenes',body);check(not replay['created'] and replay['space_id']==space,'http_duplicate_reuses_scene')
        http(manager,'/api/workspace-scenes',body|{'name':'changed'},409);check(True,'idempotency_key_cannot_change_scene')
        http(other,'/api/spaces/'+space,status=403);http(viewer,'/api/spaces/'+space,status=403)
        check(True,'direct_scene_urls_require_workspace_and_scene_grant')
        foreign_context=http(other,'/api/workspace-scenes')
        foreign=http(other,'/api/workspace-scenes',body|{'context_sha256':foreign_context['context_sha256']},201)
        check(foreign['space_id']!=space,'same_request_id_isolated_by_workspace')
        fsrc=http(other,'/api/source-settings?space_id='+foreign['space_id'])
        check([s['id'] for s in fsrc['catalog']]==['os1-single-frame'],'foreign_workspace_receives_only_allocated_source')
        http(other,'/api/source-settings',{'space_id':foreign['space_id'],'expected_revision':0,'catalog_sha256':fsrc['catalog_sha256'],
             'enabled_source_ids':['nyu-office-short'],'reason':'negative allocation test'},403)
        check(True,'unallocated_source_cannot_be_enabled')
        login(owner,'usr_owner','ws_mock',['workspace:owner'])
        octx=http(owner,'/api/workspace-scenes');check(octx['can_create'],'signed_workspace_owner_has_product_bootstrap_baseline')
        owned=http(owner,'/api/workspace-scenes',body|{'request_id':'b'*32,'context_sha256':octx['context_sha256'],'name':'Owner 空场景'},201)
        check(owned['actor']=='usr_owner','owner_creates_without_prior_scene_grant')
        settings=http(manager,'/api/source-settings?space_id='+space)
        http(manager,'/api/source-settings',{'space_id':space,'expected_revision':0,'catalog_sha256':settings['catalog_sha256'],
             'enabled_source_ids':['nyu-office-short'],'reason':'P5b empty scene to real construction'})
        entry=http(manager,'/api/inputs',{'space_id':space,'source_id':'nyu-office-short','label':'P5b办公室资料'},201)['input']
        preflight=http(manager,'/api/inputs/'+entry['id']+'/preflight',{})
        check(preflight['status']=='passed','new_scene_real_source_registration_and_preflight')
        job=http(manager,'/api/builds',{'space_id':space,'input_id':entry['id']},202)
        deadline=time.monotonic()+160
        while True:
            job=next(v for v in http(manager,'/api/builds?space_id='+space)['jobs'] if v['id']==job['id'])
            if job['state'] not in ('queued','running'):break
            if time.monotonic()>deadline:raise TimeoutError('new_scene_build_timeout')
            time.sleep(.5)
        check(job['state']=='succeeded','new_scene_actual_model_and_two_views_build')
        preview=http(manager,'/candidates/'+job['id']+'/api/preview')
        check(preview['space_id']==space,'candidate_bound_to_created_scene')
        check(http(manager,'/api/publications?space_id='+space)['publications']==[],'successful_build_does_not_auto_publish')
        config['revision']=2;config['workspaces'][0]['source_bindings'].pop('nyu-office-short');save(config_path,config)
        check(http(manager,'/api/registration-sources?space_id='+space)['sources']==[],'allocation_revocation_blocks_new_registration')
        http(manager,'/api/inputs',{'space_id':space,'source_id':'nyu-office-short','label':'revoked'},409)
        check(http(manager,'/api/inputs/'+entry['id'])['id']==entry['id'],'allocation_revocation_preserves_existing_input')
        config['revision']=3;config['workspaces'][0]['source_bindings']['nyu-office-short']=catalog.fingerprints['nyu-office-short'];save(config_path,config)
        stop();start(2)
        check(http(manager,'/api/spaces/'+space)['id']==space,'created_scene_binding_survives_actual_service_restart')
        ctx=http(manager,'/api/workspace-scenes');check(not http(manager,'/api/workspace-scenes',body|{'context_sha256':ctx['context_sha256']})['created'],
                                                      'same_request_reuses_scene_after_restart_and_configuration_revision')
        check(http(manager,'/api/inputs/'+entry['id'])['id']==entry['id'],'registered_input_survives_restart')
        check(inventory(Path('var/nyu'))==baseline,'original_engineering_records_unchanged')
        check(inventory(args.sample)==source_before,'8770_original_runtime_unchanged')
        report={'profile':'cospace.workspace-scenes-acceptance/0.1','status':'passed','passed':len(checks),'checks':checks,
            'origin':accounts.rp_origin,'runtime':str(sample),'space_id':space,'candidate_id':job['id'],'input_id':entry['id'],
            'foreign_space_id':foreign['space_id'],'owner_space_id':owned['space_id'],'identity_provider':'local_mock_only',
            'real_platform_verified':False,'quality':'unverified','production_ready':False,'robot_ready':False,
            'original_records_unchanged':len(baseline),'original_runtime_files_unchanged':len(source_before)}
        save(output/'acceptance.json',report);save(output/'http-trace.json',trace)
        print(json.dumps(report,ensure_ascii=False),flush=True)
        accounts.workspace='ws_mock';accounts.roles=['workspace:member']
        if args.stay_open:
            print('LOCAL MOCK ONLY; isolated demo remains at '+accounts.rp_origin+'/data?space='+space,flush=True)
            while process.poll() is None:time.sleep(1)
    finally:
        stop();accounts.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sample',type=Path,default=Path('var/validation/scene-construction-2026-11-03-001/runtime'))
    p.add_argument('--candidate',default='build-70889cca2d8c42e1');p.add_argument('--port',type=int,default=0)
    p.add_argument('--stay-open',action='store_true');verify(p.parse_args())
