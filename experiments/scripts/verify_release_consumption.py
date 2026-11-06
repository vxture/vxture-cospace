"""P4: real authorized scene builds/releases and independent offline consumer processes.

Creates an exclusive runtime. Reads original samples only. Identity is LOCAL MOCK.
One-shot worker failures affect this verification server only, never source files.
"""
import argparse
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, build_opener, ProxyHandler, HTTPCookieProcessor
from experiments.scripts.verify_preview_workflow import inventory
from packages.views.agent.preview_offline import OfflinePreview, sha

MODULE='experiments.scripts.verify_release_consumption'


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def serve(output,port):
    from cryptography.fernet import Fernet
    from pydantic import SecretStr
    import uvicorn
    from experiments.scripts.platform_auth_fixture import MockAccounts
    from experiments.scripts.serve_platform_workbench import assemble
    from packages.infrastructure.platform_rp import RpConfig
    from packages.infrastructure.platform_session_store import LocalRpStore
    from packages.infrastructure.space_policy_store import SpacePolicyStore
    from packages.service.platform_login import PlatformLogin
    from packages.service.space_access import SpaceAccessPolicy
    seed=json.loads((output/'seed.json').read_bytes())
    accounts=MockAccounts().start()
    try:
        accounts.roles=['workspace:member'];accounts.access_seconds=3600
        accounts.identity_options={'usr_manager':'模拟管理员','usr_local_test':'模拟查看者'}
        accounts.rp_origin=f'http://127.0.0.1:{port}'
        cfg=RpConfig(issuer=accounts.issuer,backchannel=accounts.issuer,client_id=accounts.client_id,
            client_secret=SecretStr(accounts.secret),origin=accounts.rp_origin,allow_loopback_http=True,
            encryption_key=SecretStr(Fernet.generate_key().decode()))
        auth=output/('auth-'+str(time.time_ns()))
        policies=SpacePolicyStore(auth/'policies')
        policies.replace(SpaceAccessPolicy.model_validate({
            'bindings':[{'issuer':cfg.issuer,'space_id':s,'org_id':'org_mock','workspace_id':'ws_mock'} for s in seed['scenes']],
            'grants':[{'issuer':cfg.issuer,'subject':'usr_manager','space_id':s,'role':'manager'} for s in seed['scenes']]
                +[{'issuer':cfg.issuer,'subject':'usr_local_test','space_id':seed['scenes'][0],'role':'viewer'}]}),
            expected_revision=0,actor='p4_local_mock_setup',reason='exclusive flow acceptance')
        rp=PlatformLogin(cfg,LocalRpStore(auth/'sessions',cfg.encryption_key.get_secret_value()))
        real_popen=subprocess.Popen
        def launch(command,*args,**kwargs):
            if len(command)>2 and command[2]=='experiments.scripts.derive_frozen_preview':
                task=json.loads(Path(command[command.index('--task')+1]).read_bytes())
                marker=output/('fail-next-'+task['view_kind'])
                if marker.is_file():
                    marker.unlink();command=[sys.executable,'-c','raise SystemExit(23)']
            return real_popen(command,*args,**kwargs)
        subprocess.Popen=launch
        uvicorn.run(assemble(rp,policies,output/'runtime',Path('var/nyu/office-0001a-flow-001')),
                    host='127.0.0.1',port=port,access_log=False)
    finally:accounts.stop()


def consumer(request_path):
    from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
    r=json.loads(request_path.read_bytes())
    def no_network(*args,**kwargs):raise AssertionError('consumer_network_forbidden')
    socket.socket=no_network;socket.create_connection=no_network
    root=Path(r['root']);mode=r['mode'];first,second=r['releases'];checks=[]
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    def query(session,release):
        if 'expected_source' in release:
            check(session._model.manifest.get('source')==release['expected_source'],'fixed_uploaded_source_and_batch_preserved')
        def strip(v):return {k:x for k,x in v.items() if k not in ('consumer_revision','package_sha256')}
        if 'expected_objects' in release:
            check(strip(session.objects())==release['expected_objects'],'fixed_objects_relations_and_ontology_equal_online')
            for obj in release['expected_objects']['objects']:
                check(strip(session.objects(obj['object_id']))['objects']==[obj],'fixed_object_id_lookup_equal_online')
            check(session._model.manifest.get('semantic_annotation',{}).get('ontology_ref')==release['expected_objects']['ontology_ref'],'fixed_rule_reference_in_offline_manifest')
        result={'point':strip(session.query(release['point'])),'unknown':strip(session.query(release['unknown'])),
                'range':strip(session.query_range(release['bounds'],release['frame_id'],1024))}
        check(result==release['online'],'fixed_point_unknown_range_equal_online')
        return result
    def refuse(call,code):
        try:call()
        except ValueError as exc:check(code in str(exc),'refused_'+code)
        else:raise AssertionError('expected_refusal:'+code)
    store=PersistentPreviewConsumer.initialize(root,r['space']) if mode=='install_first' else PersistentPreviewConsumer(root)
    before=store.status();results=None
    if mode=='install_first':
        store.install(first['bundle'],first['id'],first['sha256'])
        if 'expected_source' in first:
            installed=OfflinePreview.load(first['bundle'],first['id'],first['sha256'])
            check(installed.manifest.get('source')==first['expected_source'],'installed_uploaded_source_and_batch_preserved')
        check(store.status()['saved_reference'] is None and store.status()['revision']==0,'download_install_does_not_activate')
        refuse(store.session,'consumer_has_no_active_publication')
    elif mode=='activate_first':
        results=query(store.activate(first['id'],first['sha256'],0),first)
    elif mode=='restore_first':
        check(not Path(first['bundle']).exists(),'exported_zip_absent_during_restore')
        check(before['restore_required'] and before['session_reference'] is None,'restart_requires_explicit_restore')
        refuse(store.session,'consumer_has_no_active_publication')
        results=query(store.restore(first['id'],first['sha256'],r.get('expected_revision',1)),first)
    elif mode=='install_second':
        store.install(second['bundle'],second['id'],second['sha256'])
        check(store.status()['saved_reference']['publication_id']==first['id'] and store.status()['revision']==1,'new_install_keeps_old_saved_version')
        refuse(lambda:store.restore(second['id'],second['sha256'],1),'saved_reference_mismatch')
        results=query(store.restore(first['id'],first['sha256'],1),first)
    elif mode=='switch_second':
        old=store.restore(first['id'],first['sha256'],1)
        results=query(store.activate(second['id'],second['sha256'],1),second)
        query(old,first)
        check(store.status()['saved_reference']['publication_id']==second['id'] and store.status()['revision']==2,'explicit_switch_updates_reference_once')
        refuse(lambda:store.activate(first['id'],first['sha256'],1),'consumer_revision_changed')
        check(store.status()['saved_reference']['publication_id']==second['id'],'stale_switch_preserves_second')
    elif mode=='restore_second':
        check(before['session_reference'] is None and before['restore_required'],'second_restart_has_no_implicit_session')
        refuse(lambda:store.restore(first['id'],first['sha256'],2),'saved_reference_mismatch')
        results=query(store.restore(second['id'],second['sha256'],2),second)
    elif mode=='rollback_first':
        results=query(store.activate(first['id'],first['sha256'],2),first)
        check(store.status()['revision']==3,'explicit_rollback_is_new_consumer_revision')
    elif mode=='cross_scene':
        refuse(lambda:store.install(second['bundle'],second['id'],second['sha256']),'consumer_space_mismatch')
    else:raise ValueError('invalid_consumer_mode')
    save(Path(r['result']),{'mode':mode,'pid':os.getpid(),'network_disabled':True,'checks':checks,
                          'before':before,'after':store.status(),'results':results})


def run(output):
    from packages.lifecycle.preview_spaces import PreviewSpaces
    output=output.resolve();original_root=Path('var/nyu').resolve()
    if output.is_relative_to(original_root) or original_root.is_relative_to(output):
        raise ValueError('exclusive_output_outside_original_required')
    output.mkdir(parents=True,exist_ok=False)
    original=inventory(Path('var/nyu'));save(output/'original-before.json',original)
    directory=PreviewSpaces(output/'runtime/preview-directory')
    project=directory.create('project','P4 固定版本使用验收 · 本地模拟')
    space=directory.create('space','NYU 办公室 · 使用与版本更新',project['id'])['id']
    other=directory.create('space','跨场景拒绝验收',project['id'])['id']
    save(output/'seed.json',{'scenes':[space,other]})
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    origin=f'http://127.0.0.1:{port}';checks=[];trace=[];releases=[];consumer_results=[]
    def client():return build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    admin,viewer,anonymous=client(),client(),client();csrf={}
    def http(path,body=None,status=200,binary=False,c=None):
        c=c or admin;headers={}
        if body is not None:headers={'Content-Type':'application/json','Origin':origin,'X-CoSpace-CSRF':csrf.get(c,'')}
        try:
            with c.open(Request(path if path.startswith('http') else origin+path,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=50) as response:code=response.status;raw=response.read()
        except HTTPError as exc:code=exc.code;raw=exc.read()
        trace.append({'path':path.split('?')[0],'status':code,'method':'POST' if body is not None else 'GET'})
        assert code==status,(path,code,raw[:700])
        if binary:return raw
        return json.loads(raw)
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    def login(c,user):
        with c.open(origin+'/auth/login',timeout=20) as response:
            html=response.read().decode();authorize_url=response.geturl()
        link=next(value for value in re.findall(r'href="([^"]+)"',html) if 'user='+user in value)
        http(urljoin(authorize_url,link),binary=True,c=c)
        session=http('/api/auth/session',c=c);assert session['user']['subject']==user
        csrf[c]=session['csrf']
    def wait(job):
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            result=next(j for j in http('/api/builds?space_id='+space)['jobs'] if j['id']==job)
            if result['state'] not in ('running','queued'):return result
            time.sleep(.2)
        raise TimeoutError('build_timeout')
    def child(mode):
        # Third consumer store belongs to the other space; normal modes share one persistent store.
        root=output/('foreign-consumer' if mode=='cross_scene' else 'consumer')
        if mode=='cross_scene':
            from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
            PersistentPreviewConsumer.initialize(root,other)
        prefix=f'{len(consumer_results)+1:02d}-{mode}'
        target=output/(prefix+'-result.json');request=output/(prefix+'-request.json')
        save(request,{'root':str(root),'mode':mode,'space':space,'releases':releases+[{}]*(2-len(releases)),'result':str(target)})
        result=subprocess.run([sys.executable,'-X','utf8','-m',MODULE,'--consumer-request',str(request)],capture_output=True,timeout=40,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
        value=json.loads(target.read_bytes());consumer_results.append(value)
        check(value['network_disabled'] and bool(value['checks']),mode+':actual_network_disabled_process')
    with (output/'server.log').open('wb') as log:
        process=subprocess.Popen([sys.executable,'-X','utf8','-m',MODULE,'--serve','--output',str(output),'--port',str(port)],
            stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for _ in range(150):
                if process.poll() is not None:raise RuntimeError('server_exited')
                try:http('/api/auth/config',c=anonymous);break
                except URLError:time.sleep(.1)
            else:raise TimeoutError('server_start_timeout')
            http('/api/spaces',status=401,c=anonymous);check(True,'anonymous_denied')
            login(admin,'usr_manager');login(viewer,'usr_local_test')
            settings=http('/api/source-settings?space_id='+space)
            http('/api/source-settings',{'space_id':space,'expected_revision':settings['revision'],'catalog_sha256':settings['catalog_sha256'],
                'enabled_source_ids':['nyu-office-short'],'reason':'P4 固定版本流程验证'})
            entry=http('/api/inputs',{'space_id':space,'source_id':'nyu-office-short','label':'NYU 办公室原样本'},201)['input']
            check(http('/api/inputs/'+entry['id']+'/preflight',{})['status']=='passed','registered_source_preflight_passes')
            http('/api/builds',{'space_id':space,'input_id':entry['id']},403,c=viewer)
            http('/api/spaces/'+other,status=403,c=viewer);check(True,'viewer_cannot_build_or_access_foreign_space')
            for index in range(2):
                print(f'version {index+1}: authorized real model -> views -> review -> fixed release',flush=True)
                job=wait(http('/api/builds',{'space_id':space,'input_id':entry['id']},202)['id'])
                check(job['state']=='succeeded',f'v{index+1}:real_geometry_and_two_view_workers_succeed')
                body={'space_id':space,'candidate_id':job['id'],'expected_revision':index}
                if index:
                    http('/api/candidate-comparisons',body|{'expected_revision':0},409)
                    check(http('/api/selection?space_id='+space)['candidate_id']==releases[0]['candidate_id'],'stale_review_does_not_change_old_selection')
                comparison=http('/api/candidate-comparisons',body)
                http('/api/candidate-reviews',body|{'comparison_sha256':comparison['comparison_sha256'],'acknowledge_unverified':True,'note':'P4 流程验证，不代表精度或导航放行'})
                pending=http('/api/workflow?space_id='+space)
                check(pending['next_stage']=='delivery' and pending['publication_ref'] is None,f'v{index+1}:optional_semantics_do_not_block_and_old_release_not_borrowed')
                http('/api/publications',body|{'expected_revision':index+1},403,c=viewer)
                http('/api/publications',body|{'expected_revision':index},409)
                publication=http('/api/publications',body|{'expected_revision':index+1},201)
                info=http(publication['preview_url']+'offline.json');raw=http(publication['preview_url']+'offline.zip',binary=True)
                check(sha(raw)==info['sha256'],f'v{index+1}:download_digest_matches_fixed_release')
                offline=OfflinePreview(raw,publication['id'],info['sha256']);cell=sorted(offline.cells)[0];resolution=offline.resolution
                point=[(v+.5)*resolution for v in cell];unknown=[100000.,100000.,100000.]
                bounds=[[v*resolution for v in cell],[(v+1)*resolution for v in cell]]
                online={'point':http(publication['query_url'],{'point_m':point}),
                    'unknown':http(publication['query_url'],{'point_m':unknown}),
                    'range':http(publication['preview_url']+'api/query-range',{'bounds_m':bounds,'frame_id':offline.manifest['frame_id'],'limit':1024})}
                check(online['range']['result_complete'] and online['unknown']['state']=='unknown',f'v{index+1}:range_complete_unknown_not_free')
                bundle=output/f'v{index+1}.zip';bundle.write_bytes(raw)
                releases.append({'id':publication['id'],'candidate_id':job['id'],'frozen_model':job['frozen_model'],'sha256':info['sha256'],
                    'bundle':str(bundle),'point':point,'unknown':unknown,'bounds':bounds,'frame_id':offline.manifest['frame_id'],'online':online})
                flow=http('/api/workflow?space_id='+space)
                check(flow['next_stage']=='space' and flow['summary']['service_status']=='complete' and not flow['consumer_state_checked'],f'v{index+1}:published_geometric_flow_reaches_consumption_without_claiming_device_state')
                if not index:
                    child('install_first');child('activate_first');bundle.rename(output/'v1-export-evidence.zip');child('restore_first')
                else:
                    check(releases[0]['frozen_model']!=job['frozen_model'],'second_build_has_own_fixed_model_identity')
                    child('install_second');child('switch_second');child('restore_second');child('cross_scene')
            old,new=releases
            check(http(f"/publications/{old['id']}/offline.zip",binary=True)==(output/'v1-export-evidence.zip').read_bytes(),'historical_release_bytes_unchanged_after_second_release')
            http('/api/builds',{'space_id':other,'input_id':entry['id']},403)
            http('/api/publications',{'space_id':other,'candidate_id':new['candidate_id'],'expected_revision':2},403)
            http(f"/publications/{new['id']}/offline.zip",status=403,c=viewer)
            check(True,'cross_scene_references_and_viewer_export_rejected')
            (output/'fail-next-human').write_text('exclusive worker exit23')
            failed=wait(http('/api/builds',{'space_id':space,'input_id':entry['id']},202)['id'])
            check(failed['state']=='views_failed' and http('/api/selection?space_id='+space)['candidate_id']==new['candidate_id'],'failed_third_build_does_not_replace_selected_release')
            check(http(f"/publications/{old['id']}/api/query",{'point_m':old['point']})==old['online']['point'] and
                http(f"/publications/{new['id']}/api/query",{'point_m':new['point']})==new['online']['point'],'both_fixed_releases_readable_after_failed_third_build')
            artifact='publication:'+new['id']
            control=http('/api/artifact-control?space_id='+space+'&artifact='+artifact)
            transition={'space_id':space,'artifact':artifact,'expected_revision':control['record']['revision'],
                'expected_snapshot_sha256':control['snapshot_sha256'],'operation':'pause_distribution','reason':'P4 暂停新分发，不撤销已安装离线快照'}
            http('/api/artifact-control/transitions',transition,403,c=viewer)
            http('/api/artifact-control/transitions',transition)
            http(f"/publications/{new['id']}/api/query",{'point_m':new['point']},409)
            http(f"/publications/{new['id']}/offline.zip",status=409)
            check(http('/api/workflow?space_id='+space)['next_stage']=='delivery','paused_current_release_requires_explicit_recovery_no_old_fallback')
            child('restore_second');check(True,'already_installed_offline_version_survives_server_pause')
            control=http('/api/artifact-control?space_id='+space+'&artifact='+artifact)
            http('/api/artifact-control/transitions',transition|{'operation':'restore','expected_revision':control['record']['revision'],
                 'expected_snapshot_sha256':control['snapshot_sha256']})
            check(http(f"/publications/{new['id']}/offline.zip",binary=True)==Path(new['bundle']).read_bytes(),'explicit_distribution_restore_preserves_exact_package')
            child('rollback_first')
            check(http('/api/workflow?space_id='+space)['consumer_state_checked'] is False,'server_never_infers_consumer_activation_from_export_or_local_evidence')
            check(inventory(Path('var/nyu'))==original,'original_195_engineering_records_unchanged')
            report={'profile':'cospace.release-consumption-acceptance/0.1','status':'passed','passed':len(checks),'checks':checks,
                'runtime':str(output/'runtime'),'space_id':space,'other_space_id':other,'input_id':entry['id'],
                'candidate_id':new['candidate_id'],'publication_id':new['id'],'failed_build_id':failed['id'],'releases':releases,
                'consumer_processes':[{'mode':r['mode'],'pid':r['pid'],'checks':r['checks']} for r in consumer_results],
                'identity_provider':'local_mock_only','transport':'real_authorized_loopback_HTTP','quality':'unverified',
                'production_ready':False,'robot_ready':False,'original_records_unchanged':len(original)}
            save(output/'http-trace.json',trace);save(output/'acceptance.json',report)
            print(json.dumps(report,ensure_ascii=False),flush=True)
        finally:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    parser.add_argument('--serve',action='store_true');parser.add_argument('--port',type=int,default=8773)
    parser.add_argument('--consumer-request',type=Path);args=parser.parse_args()
    if args.consumer_request:consumer(args.consumer_request)
    elif args.output is None:parser.error('--output required')
    elif args.serve:serve(args.output.resolve(),args.port)
    else:run(args.output)
