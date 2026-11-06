"""Two-user authorized sample HTTP flow, local mock IdP, durable policy revocation."""
import argparse
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
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import build_opener, ProxyHandler, HTTPCookieProcessor, Request
from experiments.scripts.serve_platform_workbench_mock import setup
from packages.service.space_access import SpaceAccessPolicy


def verify(output, with_settings=False, with_sources=False, with_preparation=False):
    output=Path(output).resolve()
    baseline=json.loads(Path('experiments/evidence/2026-11-03/preview-lifecycle-h3c-001/original-before.json').read_bytes())
    def unchanged():return all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in baseline.items())
    if output.exists():raise ValueError('new_output_required')
    if not unchanged():raise ValueError('sample_baseline_changed')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    accounts,rp,policies,sample,initial=setup(output,port)
    origin=rp.config.origin
    env=os.environ.copy();env.update(COSPACE_OIDC_ISSUER=rp.config.issuer,COSPACE_OIDC_BACKCHANNEL=rp.config.backchannel,
        COSPACE_OIDC_CLIENT_ID=rp.config.client_id,COSPACE_OIDC_CLIENT_SECRET=rp.config.client_secret.get_secret_value(),
        COSPACE_ORIGIN=origin,COSPACE_SESSION_KEY=rp.config.encryption_key.get_secret_value(),COSPACE_OIDC_LOOPBACK_HTTP='1')
    checks=[];trace=[];process=log=None;process_count=0
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    def client():return build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    def request(c,path,body=None,csrf=None):
        headers={}
        if body is not None:headers={'Content-Type':'application/json','Origin':origin,'X-CoSpace-CSRF':csrf or ''}
        url=path if path.startswith('http') else origin+path
        try:r=c.open(Request(url,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=15)
        except HTTPError as e:r=e
        with r:status,raw=r.status,r.read()
        trace.append({'method':'POST' if body is not None else 'GET','path':urlsplit(url).path,'status':status})
        try:data=json.loads(raw)
        except ValueError:data=raw
        return status,data
    def login(c,user):
        status,html=request(c,'/auth/login');check('mock_authorize:'+user,status==200)
        link=next(value for value in re.findall(r'href="([^"]+)"',html.decode()) if 'user='+user in value)
        status,_=request(c,urljoin(accounts.issuer,link));check('callback:'+user,status==200)
        status,data=request(c,'/api/auth/session');check('verified_subject:'+user,data['user']['subject']==user)
        return data['csrf']
    def stop():
        nonlocal process,log
        if process and process.poll() is None:process.terminate();process.wait(timeout=10)
        if log:log.close()
        process=log=None
    def start():
        nonlocal process,log,process_count
        process_count+=1;log=(output/f'server-{process_count}.log').open('wb')
        process=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.serve_platform_workbench',
            '--runtime',str(output/'auth'),'--sample',str(sample),'--initial',str(initial),'--port',str(port)],
            env=env,stdout=log,stderr=subprocess.STDOUT)
        until=time.monotonic()+20
        while time.monotonic()<until:
            if process.poll() is not None:raise RuntimeError('authorized_service_start_failed')
            try:
                if request(client(),'/api/auth/config')[0]==200:return
            except (OSError,URLError):time.sleep(.1)
        raise RuntimeError('authorized_service_timeout')
    try:
        start();a,b,manager,anonymous=client(),client(),client(),client()
        check('anonymous_directory_denied',request(anonymous,'/api/spaces')[0]==401)
        csrf_a=login(a,'usr_local_test');csrf_b=login(b,'usr_other');csrf_m=login(manager,'usr_manager')
        if with_sources:
            _,visible_a=request(a,'/api/spaces');_,visible_b=request(b,'/api/spaces')
            identity=visible_a['spaces'][0]['id'];other=visible_b['spaces'][0]['id']
            query='?'+urlencode({'space_id':identity});other_query='?'+urlencode({'space_id':other})
            before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('preview-builds','preview-inputs') for p in (sample/folder).rglob('*') if p.is_file()}
            check('sources_anonymous_denied',request(anonymous,'/api/source-settings'+query)[0]==401)
            check('sources_require_explicit_space',request(manager,'/api/registration-sources')[0]==403)
            check('viewer_cannot_read_source_catalog',request(a,'/api/source-settings'+query)[0]==403)
            check('foreign_engineer_cannot_read_sources',request(b,'/api/registration-sources'+query)[0]==403)
            _,settings=request(manager,'/api/source-settings'+query)
            check('source_default_deny',settings['revision']==0 and settings['sources']==[])
            check('source_catalog_has_two_adapters',set(s['id'] for s in settings['catalog'])=={'nyu-office-short','os1-single-frame'})
            check('source_catalog_hides_paths','snapshot' not in json.dumps(settings) and 'tracking' not in json.dumps(settings))
            payload={'space_id':identity,'expected_revision':0,'catalog_sha256':settings['catalog_sha256'],
                     'enabled_source_ids':['os1-single-frame'],'reason':'I5 真实HTTP启用激光来源'}
            register={'space_id':identity,'source_id':'os1-single-frame','label':'I5 激光流程输入'}
            check('disabled_source_registration_denied',request(manager,'/api/inputs',register,csrf_m)[0]==409)
            check('source_settings_csrf_required',request(manager,'/api/source-settings',payload)[0]==403)
            check('engineer_source_settings_write_denied',request(b,'/api/source-settings',dict(payload,space_id=other),csrf_b)[0]==403)
            check('stale_catalog_conflict',request(manager,'/api/source-settings',dict(payload,catalog_sha256='0'*64),csrf_m)[0]==409)
            status,configured=request(manager,'/api/source-settings',payload,csrf_m)
            check('manager_enables_space_source',status==200 and configured['revision']==1 and configured['history'][0]['actor']=='usr_manager')
            check('source_revision_conflict',request(manager,'/api/source-settings',payload,csrf_m)[0]==409)
            check('enabled_source_visible_for_registration',request(manager,'/api/registration-sources'+query)[1]['sources'][0]['id']=='os1-single-frame')
            status,registered=request(manager,'/api/inputs',register,csrf_m)
            check('new_laser_input_registered',status==201 and registered['created'])
            input_id=registered['input']['id']
            if with_preparation:
                check_endpoint=f'/api/inputs/{input_id}/preflight'
                flow='/api/workflow?'+urlencode({'space_id':identity,'input_id':input_id})
                check('check_default_unobserved',request(manager,check_endpoint)[1]['last_check'] is None)
                check('check_csrf_required',request(manager,check_endpoint,{})[0]==403)
                check('viewer_check_denied',request(a,check_endpoint)[0]==403)
                check('foreign_engineer_check_denied',request(b,check_endpoint)[0]==403)
                status,checked=request(manager,check_endpoint,{},csrf_m)
                check('real_preflight_saved',status==200 and checked['status']=='passed' and checked['actor']=='usr_manager' and checked['sequence']>=1)
                _,progress=request(manager,flow)
                check('workflow_follows_explicit_input',progress['preparation']['selected_input_id']==input_id and progress['preparation']['next_action']['values']['input']==input_id)
                check('workflow_suggests_build_from_saved_check',progress['preparation']['next_action']['module']=='build')
                check('workflow_does_not_claim_current_files_or_poll',not progress['preparation']['current_files_checked'] and not progress['jobs_polled'])
                check('viewer_flow_hides_engineering_preparation','preparation' not in request(a,'/api/workflow'+query)[1])
            check('input_records_admitted_source_revision',registered['input']['registration_ref']=={
                'source_id':'os1-single-frame','settings_revision':1,'catalog_sha256':settings['catalog_sha256'],'actor':'usr_manager'})
            status,duplicate=request(manager,'/api/inputs',register,csrf_m)
            check('source_registration_idempotent',status==200 and not duplicate['created'] and duplicate['input']['id']==input_id)
            check('manager_enables_engineer_space_source',request(manager,'/api/source-settings',dict(payload,space_id=other,enabled_source_ids=['nyu-office-short']),csrf_m)[0]==200)
            _,engineer_settings=request(b,'/api/source-settings'+other_query)
            check('engineer_reads_only_enabled_sources',not engineer_settings['can_manage'] and engineer_settings['history']==engineer_settings['catalog']==[] and len(engineer_settings['sources'])==1)
            status,engineer_input=request(b,'/api/inputs',{'space_id':other,'source_id':'nyu-office-short','label':'I5 工程师登记RGB-D'},csrf_b)
            check('engineer_registers_authorized_source',status==201 and engineer_input['input']['registration_ref']['actor']=='usr_other')
            stop();start()
            check('source_settings_survive_restart',request(manager,'/api/source-settings'+query)[1]['revision']==1)
            check('source_input_binding_survives_restart',request(manager,'/api/inputs/'+input_id)[1]['registration_ref']['settings_revision']==1)
            if with_preparation:
                latest=request(manager,check_endpoint)[1]['last_check']
                check('saved_check_survives_actual_restart',latest['status']=='passed' and latest['registration_matches'] and latest['actor']=='usr_manager')
                path=sample/'preview-inputs'/(input_id+'.json');raw=path.read_bytes();value=json.loads(raw)
                value['label']='Isolated registration mismatch verification';path.write_text(json.dumps(value),encoding='utf-8')
                check('changed_registration_does_not_borrow_old_pass',request(manager,check_endpoint)[1]['last_check']['registration_matches'] is False)
                _,changed=request(manager,flow)
                check('workflow_recommends_recheck_for_changed_registration',changed['preparation']['next_action']['module']=='data')
                path.write_bytes(raw)
                check('original_input_restore_retains_own_evidence',request(manager,check_endpoint)[1]['last_check']['registration_matches'])
            check('manager_disables_new_registration',request(manager,'/api/source-settings',dict(payload,expected_revision=1,enabled_source_ids=[]),csrf_m)[0]==200)
            check('previously_selected_source_refused_after_disable',request(manager,'/api/inputs',register,csrf_m)[0]==409)
            check('disabled_sources_removed_from_registration_list',request(manager,'/api/registration-sources'+query)[1]['sources']==[])
            check('registered_input_still_available',request(manager,'/api/inputs/'+input_id)[0]==200)
            status,job=request(manager,'/api/builds',{'space_id':identity,'input_id':input_id},csrf_m)
            check('existing_input_build_admitted_after_source_disable',status==202)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                _,listing=request(manager,'/api/builds'+query)
                job=next(j for j in listing['jobs'] if j['id']==job['id'])
                if job['state'] in ('succeeded','failed'):break
                time.sleep(.4)
            check('actual_laser_build_succeeds',job['state']=='succeeded')
            _,model=request(manager,'/candidates/'+job['id']+'/api/preview')
            check('candidate_retains_input_source_binding',model['source']['input_binding']['registration_ref']['settings_revision']==1)
            check('existing_inputs_builds_and_releases_unchanged',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==value for p,value in before.items()))
            stop();start()
            check('source_disable_and_history_survive_restart',request(manager,'/api/source-settings'+query)[1]['revision']==2)
        if with_settings:
            _,visible_a=request(a,'/api/spaces');_,visible_b=request(b,'/api/spaces')
            identity=visible_a['spaces'][0]['id'];other=visible_b['spaces'][0]['id']
            endpoint='/api/space-settings?'+urlencode({'space_id':identity})
            check('anonymous_settings_denied',request(anonymous,endpoint)[0]==401)
            _,settings=request(manager,endpoint);original=settings['space']
            check('manager_settings_revision_zero',settings['revision']==0 and settings['can_manage'])
            payload={'space_id':identity,'expected_revision':0,'name':original['name']+' · 配置验证',
                     'description':'隔离副本：空间基本配置验证','reason':'真实HTTP配置闭环'}
            before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (sample/'preview-builds').rglob('*') if p.is_file()}
            check('viewer_settings_write_denied',request(a,'/api/space-settings',payload,csrf_a)[0]==403)
            check('engineer_settings_write_denied',request(b,'/api/space-settings',dict(payload,space_id=other),csrf_b)[0]==403)
            check('settings_csrf_required',request(manager,'/api/space-settings',payload)[0]==403)
            status,updated=request(manager,'/api/space-settings',payload,csrf_m)
            check('manager_saves_real_settings',status==200 and updated['revision']==1)
            check('settings_audit_actor_from_verified_identity',updated['history'][0]['actor']=='usr_manager' and updated['history'][0]['reason']==payload['reason'])
            check('settings_stale_revision_conflict',request(manager,'/api/space-settings',dict(payload,name='stale'),csrf_m)[0]==409)
            _,view=request(a,endpoint)
            check('viewer_reads_new_settings_without_admin_history',view['space']['name']==payload['name'] and not view['can_manage'] and view['history']==[])
            check('foreign_settings_hidden',request(b,endpoint)[0]==403)
            _,listing=request(a,'/api/spaces')
            check('directory_reflects_saved_name',listing['spaces'][0]['name']==payload['name'])
            stop();start()
            _,restored=request(manager,endpoint)
            check('settings_survive_real_restart',restored['revision']==1 and restored['space']['name']==payload['name'] and len(restored['history'])==1)
            restore=dict(payload,expected_revision=1,name=original['name'],description=original['description'],reason='验证后恢复原展示信息')
            status,restored=request(manager,'/api/space-settings',restore,csrf_m)
            check('settings_explicit_restore_has_history',status==200 and restored['revision']==2 and len(restored['history'])==2)
            after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (sample/'preview-builds').rglob('*') if p.is_file()}
            check('settings_leave_all_model_and_release_files_unchanged',before==after)
        _,da=request(a,'/api/spaces');_,db=request(b,'/api/spaces')
        check('two_users_have_distinct_single_space',len(da['spaces'])==len(db['spaces'])==1 and da['spaces'][0]['id']!=db['spaces'][0]['id'])
        sa,sb=da['spaces'][0],db['spaces'][0];pa,pb=sa['publication_id'],sb['publication_id']
        check('viewer_own_human_view',request(a,f'/publications/{pa}/human.ply')[0]==200)
        check('viewer_own_views_data',request(a,f'/publications/{pa}/views.js')[0]==200)
        check('viewer_offline_export_denied',request(a,f'/publications/{pa}/offline.zip')[0]==403)
        check('viewer_foreign_direct_publication_denied',request(a,f'/publications/{pb}/api/preview')[0]==403)
        check('engineer_foreign_direct_publication_denied',request(b,f'/publications/{pa}/api/preview')[0]==403)
        check('engineer_own_offline_export',request(b,f'/publications/{pb}/offline.zip')[0]==200)
        check('viewer_query_allowed',request(a,f'/publications/{pa}/api/query',{'point_m':[0,0,0]},csrf_a)[0]==200)
        check('viewer_build_denied',request(a,'/api/builds',{'space_id':sa['id'],'input_id':'input-'+'f'*16},csrf_a)[0]==403)
        check('engineer_publish_denied',request(b,'/api/publications',{'space_id':sb['id'],'candidate_id':sb['publications'][0]['candidate_id'],'expected_revision':0},csrf_b)[0]==403)
        check('legacy_root_asset_denied',request(a,'/spatial.npz')[0]==403)
        _,selection=request(manager,'/api/selection?'+urlencode({'space_id':sa['id']}))
        status,new=request(manager,'/api/publications',{'space_id':sa['id'],'candidate_id':selection['candidate_id'],'expected_revision':selection['revision']},csrf_m)
        check('manager_publishes_fixed_selected_candidate',status==201)
        artifact='publication:'+new['id'];query=urlencode({'space_id':sa['id'],'artifact':artifact})
        _,report=request(manager,'/api/artifact-control?'+query)
        change={'space_id':sa['id'],'artifact':artifact,'expected_revision':0,'expected_snapshot_sha256':report['snapshot_sha256'],
                'operation':'pause_distribution','reason':'isolated authorization acceptance'}
        check('manager_pauses_publication',request(manager,'/api/artifact-control/transitions',change,csrf_m)[0]==200)
        check('authorized_viewer_obeys_distribution_pause',request(a,f"/publications/{new['id']}/human.ply")[0]==409)
        check('foreign_user_denied_before_pause_state',request(b,f"/publications/{new['id']}/human.ply")[0]==403)
        revision,policy=policies.load();value=policy.model_dump();value['grants']=[g for g in value['grants'] if g['subject']!='usr_local_test']
        policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=revision,actor='acceptance',reason='revoke viewer')
        check('revocation_applies_without_restart',request(a,f'/publications/{pa}/human.ply')[0]==403)
        check('revoked_viewer_directory_empty',request(a,'/api/spaces')[1]['spaces']==[])
        stop();start()
        check('policy_revocation_survives_real_restart',request(a,'/api/spaces')[1]['spaces']==[])
        check('other_user_session_and_access_survive_restart',request(b,f'/publications/{pb}/offline.zip')[0]==200)
        check('original_195_files_unchanged',unchanged())
        report={'profile':'cospace.space-preparation-i6-acceptance/0.1' if with_preparation else 'cospace.space-sources-i5-acceptance/0.1' if with_sources else 'cospace.space-settings-i4-acceptance/0.1' if with_settings else 'cospace.platform-access-i3-acceptance/0.1','identity_provider':'local_mock_only',
            'real_platform_authenticated':False,'checks':checks,'http_requests':len(trace),'service_processes':process_count,
            'historical_files_checked':len(baseline),'sample_copy':str(sample),'policy_revision':policies.load()[0]}
        (output/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (output/'http-trace-redacted.json').write_text(json.dumps(trace,indent=2)+'\n',encoding='utf-8')
        return report
    finally:stop();accounts.stop()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--with-settings',action='store_true');p.add_argument('--with-sources',action='store_true');p.add_argument('--with-preparation',action='store_true');a=p.parse_args();report=verify(a.output,a.with_settings,a.with_sources or a.with_preparation,a.with_preparation)
    print(json.dumps({'passed':len(report['checks']),'http_requests':report['http_requests'],
        'service_processes':report['service_processes'],'historical_files_checked':report['historical_files_checked']}))


if __name__=='__main__':main()
