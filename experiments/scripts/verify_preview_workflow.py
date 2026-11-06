"""Run the six-module reference workflow in an exclusive isolated output directory.

Uses real HTTP, real build subprocesses and a separate network-disabled consumer process.
Existing local sources are read only. Never run against the original runtime root.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_ledger import PreviewLedger
from packages.data.preview_source_config import load_sources
from packages.construction.preview_jobs import PreviewJobs
from packages.ontology.preview_versions import PreviewOntologies
from packages.views.agent.preview_offline import OfflinePreview,sha

PROFILE='cospace.preview-workflow-acceptance/0.1'
MODULE='experiments.scripts.verify_preview_workflow'
def inventory(root):
    return {p.as_posix():sha(p.read_bytes()) for name in ('preview-builds','preview-directory','preview-inputs','preview-ontologies','preview-ledger')
            for p in (root/name).rglob('*') if p.is_file()}

def app_at(output,base,sources_config):
    from experiments.scripts.serve_nyu_flow_preview import create_app
    root=output/'runtime';directory=PreviewSpaces(root/'preview-directory');inputs=PreviewInputs(root/'preview-inputs',directory)
    jobs=PreviewJobs(root/'preview-builds',Path('.'),Path('.'),inputs);ontologies=PreviewOntologies(root/'preview-ontologies')
    for seed in ('configs/ontology/indoor-equipment-v0.1.json','configs/ontology/indoor-equipment-v0.2.json'):ontologies.register(seed)
    sources,status=load_sources(sources_config,Path.cwd())
    return create_app(base,jobs,registration_sources=sources,source_config_status=status,space_directory=directory,
                      ontologies=ontologies,ledger=PreviewLedger(root/'preview-ledger',directory))

def consumer_child(request_path):
    from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
    request=json.loads(request_path.read_bytes())
    def no_network(*a,**k):raise AssertionError('consumer_network_forbidden')
    socket.socket=no_network;socket.create_connection=no_network
    root=Path(request['consumer']);space=request['space'];pub=request['publication'];digest=request['sha256']
    if request['mode']=='install':
        store=PersistentPreviewConsumer.initialize(root,space);store.install(Path(request['bundle']),pub,digest)
        before=store.status();session=store.activate(pub,digest,0)
        assert before['saved_reference'] is None and before['session_reference'] is None
    else:
        assert not Path(request['bundle']).exists()
        store=PersistentPreviewConsumer(root);before=store.status();session=store.restore(pub,digest,1)
        assert before['restore_required'] and before['session_reference'] is None
    def strip(result):return {k:v for k,v in result.items() if k not in ('consumer_revision','package_sha256')}
    results={'objects':strip(session.objects()),'point':strip(session.query(request['point'])),
             'range':strip(session.query_range(request['bounds'],request['frame_id'],1024))}
    # Consumer metadata is checked separately from the publication's response.
    assert not store.status()['restore_required'] and store.status()['revision']==1
    value={'network_disabled':True,'pid':os.getpid(),'mode':request['mode'],'status_before':before,'status_after':store.status(),'results':results}
    Path(request['result']).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    original=inventory(Path('var/nyu'));(output/'original-before.json').write_text(json.dumps(original,indent=2)+'\n',encoding='utf-8')
    # Initialize the exclusive new runtime, then serve it in another process.
    app_at(output,args.base,args.sources_config)
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    log=(output/'server.log').open('wb');server=subprocess.Popen([sys.executable,'-X','utf8','-m',MODULE,
        '--serve','--output',str(output),'--base',str(args.base),'--sources-config',str(args.sources_config),'--port',str(port)],
        stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    origin=f'http://127.0.0.1:{port}';checks=[];samples=[]
    def http(path,body=None,expected=200,binary=False):
        data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
        try:
            with urlopen(Request(origin+path,data=data,headers={'Content-Type':'application/json'}),timeout=45) as response:status=response.status;raw=response.read()
        except HTTPError as error:status=error.code;raw=error.read()
        assert status==expected,(path,status,raw[:1000])
        return raw if binary else json.loads(raw)
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    def review(space,candidate,revision):
        body={'space_id':space,'candidate_id':candidate,'expected_revision':revision}
        comparison=http('/api/candidate-comparisons',body)
        http('/api/candidate-reviews',body|{'comparison_sha256':comparison['comparison_sha256'],'acknowledge_unverified':True,'note':'六入口流程验收；对象、台账、关系均为测试声明，未现场核实'})
        return comparison
    try:
        for _ in range(100):
            if server.poll() is not None:raise RuntimeError('acceptance_server_exited')
            try:http('/api/projects');break
            except URLError:time.sleep(.1)
        else:raise RuntimeError('acceptance_server_start_timeout')
        project=http('/api/projects',{'name':'六入口流程验收 · 公开样本'},201)
        foreign=http('/api/spaces',{'name':'隔离负例空间','project_id':project['id'],'description':'只用于跨空间引用拒绝'},201)
        rules=http('/api/ontologies')['ontologies'];rule=next(r for r in rules if r['version']=='0.2.0');ref={k:rule[k] for k in ('ontology_id','version','sha256')}
        for label,source_id in [('laser','os1-single-frame'),('nyu','nyu-office-short')]:
            print(label+': register → real build',flush=True)
            space=http('/api/spaces',{'name':label+' · 端到端流程验证','project_id':project['id'],'description':'独立工程验收；非现场设备及关系资料'},201)['id']
            empty=http('/api/workflow?space_id='+space);check(empty['next_stage']=='data',label+': empty_space_starts_with_data')
            registered=http('/api/inputs',{'space_id':space,'source_id':source_id,'label':label+' 封存流程资料'},201)['input']
            duplicate=http('/api/inputs',{'space_id':space,'source_id':source_id,'label':'重复登记不得覆盖'})
            check(not duplicate['created'] and duplicate['input']['id']==registered['id'],label+': registration_deduplicated')
            preflight=http('/api/inputs/'+registered['id']+'/preflight',{})
            check(preflight['status']=='passed',label+': source_preflight_passed')
            batch=None
            if args.with_batches:
                batch=http('/api/batches',{'space_id':space,'name':label+' · 导入批次','origin':'imported_sample','note':'公开封存样本，非现场采集'},201)
                def transition(current,operation,**values):
                    return http('/api/batches/'+current['id']+'/transitions',{'space_id':space,'expected_revision':current['revision'],'operation':operation,'reason':'批次流程验收',**values})
                batch=transition(batch,'replace_members',input_ids=[registered['id']])
                http('/api/builds',{'space_id':space,'input_id':registered['id']},409)
                http('/api/builds',{'space_id':space,'input_id':registered['id'],'batch_id':batch['id'],'batch_revision':batch['revision']},409)
                check(True,label+': draft_and_omitted_batch_rejected')
                batch=transition(batch,'seal')
                before=http('/api/batches/'+batch['id']+'?space_id='+space)
                check(before['batch']['state']=='sealed' and before['attempts']==[],label+': sealed_with_no_retroactive_attempts')
            http('/api/builds',{'space_id':foreign['id'],'input_id':registered['id']},409);check(True,label+': cross_space_build_rejected')
            job=http('/api/builds',{'space_id':space,'input_id':registered['id'],**({'batch_id':batch['id'],'batch_revision':batch['revision']} if batch else {})},202);geometry=job['id']
            deadline=time.monotonic()+135
            while True:
                job=next(j for j in http('/api/builds?space_id='+space)['jobs'] if j['id']==geometry)
                if job['state'] not in ('running','queued'):break
                if time.monotonic()>deadline:raise TimeoutError('real_build_timeout')
                time.sleep(.25)
            check(job['state']=='succeeded',label+': actual_build_subprocess_succeeded')
            if batch:
                check(job['batch_ref']==http('/candidates/'+geometry+'/api/preview')['source']['batch_ref'],label+': geometry_preserves_admitted_batch_ref')
            geometric=http('/candidates/'+geometry+'/api/preview');anchor=http('/candidates/'+geometry+'/api/anchor?point_index=0')
            check(http('/api/workflow?space_id='+space)['candidate_ref'] is None,label+': build_does_not_select')
            objects=[{'object_id':identity,'type_id':kind,'properties':{'name':title+' · 流程测试，待核实'},'point_index':i}
                     for i,(identity,kind,title) in enumerate([('g1-room','room','测试设备间'),('g1-cabinet','cabinet','测试设备柜'),('g1-corridor','corridor','测试走廊'),('g1-inspection','inspection_point','测试巡检点')])]
            validation=http(f"/api/ontologies/{ref['ontology_id']}/{ref['version']}/validate",{'sha256':ref['sha256'],'objects':[{k:v for k,v in o.items() if k!='point_index'} for o in objects]})
            check(validation['status']=='passed' and validation['saved'] is False,label+': fixed_ontology_draft_validation')
            semantic=http('/api/semantic-candidates',{'space_id':space,'base_candidate_id':geometry,'base_manifest_sha256':anchor['model_manifest_sha256'],'ontology_ref':ref,'objects':objects},201)['id']
            entry=http('/api/ledger',{'space_id':space,'source_system':'acceptance-local','external_id':'TEST-'+label,'version':'1','title':'流程测试设备台账 · 非现场资料','fields':{'asset_code':'TEST-'+label}},201)
            anchor=http('/candidates/'+semantic+'/api/anchor?point_index=0')
            business=http('/api/business-candidates',{'space_id':space,'base_candidate_id':semantic,'base_manifest_sha256':anchor['model_manifest_sha256'],'bindings':[{'object_id':'g1-cabinet','ledger_ref':entry['ref']}]},201)['id']
            relations=[{'relation_id':'g1-contains','type_id':'contains','source_id':'g1-room','target_id':'g1-cabinet','note':'人工流程测试归属，未现场确认'},
                       {'relation_id':'g1-located','type_id':'located_in','source_id':'g1-inspection','target_id':'g1-room','note':'人工流程测试点位，未现场确认'},
                       {'relation_id':'g1-connect','type_id':'connected_to','source_id':'g1-room','target_id':'g1-corridor','note':'人工流程连接，不表示可通行'}]
            anchor=http('/candidates/'+business+'/api/anchor?point_index=0');body={'space_id':space,'base_candidate_id':business,'base_manifest_sha256':anchor['model_manifest_sha256'],'ontology_ref':ref,'relations':relations}
            rejected=http('/api/relation-candidates',body|{'relations':relations+[relations[0]|{'relation_id':'duplicate-test','type_id':'located_in','source_id':'g1-cabinet','target_id':'g1-room'}]},422)
            check(any(i['code']=='duplicate_relation_assertion' for i in rejected['detail']['issues']),label+': duplicate_inverse_relation_rejected')
            candidate=http('/api/relation-candidates',body,201)['id']
            http('/api/publications',{'space_id':space,'candidate_id':candidate,'expected_revision':0},409);check(True,label+': unselected_publication_rejected')
            comparison=review(space,candidate,0)
            check(len(comparison['business']['added'])==1 and len(comparison['relations']['added'])==3,label+': review_contains_business_and_relations')
            publication=http('/api/publications',{'space_id':space,'candidate_id':candidate,'expected_revision':1},201)['id']
            current=http('/api/workflow?space_id='+space)
            check(all(s['status'] in ('recorded','ready') for s in current['stages'] if s['id']!='consumer'),label+': six_modules_saved_flow_recorded')
            check(current['next_stage']=='space' and current['summary']['service_status']=='complete' and not current['consumer_state_checked'],label+': consumer_not_inferred_from_download')
            check(current['counts']['objects']==4 and current['counts']['business_bindings']==1 and current['counts']['object_relations']==3,label+': selected_snapshot_counts_exact')
            checklist=http(f'/publications/{publication}/api/checklist');check(next(s for s in checklist['stages'] if s['id']=='query')['status']=='passed',label+': fixed_checklist_includes_object_snapshot')
            print(label+': HTTP queries → network-disabled consumer processes',flush=True)
            info=http(f'/publications/{publication}/offline.json');raw=http(f'/publications/{publication}/offline.zip',binary=True)
            check(info['profile']=='cospace.preview-offline/0.4' and sha(raw)==info['sha256'],label+': offline_0_4_package_integrity')
            sample_dir=output/label;sample_dir.mkdir();bundle=sample_dir/'offline.zip';bundle.write_bytes(raw)
            offline=OfflinePreview(raw,publication,sha(raw));cell=sorted(offline.cells)[0];resolution=offline.resolution
            point=[(v+.5)*resolution for v in cell];bounds=[[v*resolution for v in cell],[(v+1)*resolution for v in cell]]
            online={'objects':http(f'/publications/{publication}/api/objects'),
                    'point':http(f'/publications/{publication}/api/query',{'point_m':point}),
                    'range':http(f'/publications/{publication}/api/query-range',{'bounds_m':bounds,'frame_id':offline.manifest['frame_id'],'limit':1024})}
            check(len(online['objects']['relations'])==3 and any(o.get('business_links') for o in online['objects']['objects']),label+': published_relations_and_business_together')
            check(online['range']['result_complete'],label+': bounded_range_query_complete')
            outputs=[]
            for mode in ('install','restore'):
                if mode=='restore':bundle.rename(sample_dir/'exported-evidence.zip')
                request={'mode':mode,'bundle':str(bundle),'consumer':str(sample_dir/'consumer'),'space':space,'publication':publication,'sha256':sha(raw),
                         'point':point,'bounds':bounds,'frame_id':offline.manifest['frame_id'],'result':str(sample_dir/(mode+'-result.json'))}
                request_path=sample_dir/(mode+'-request.json');request_path.write_text(json.dumps(request),encoding='utf-8')
                subprocess.run([sys.executable,'-X','utf8','-m',MODULE,'--consumer-request',str(request_path)],check=True,timeout=30,
                               capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                result=json.loads(Path(request['result']).read_bytes());outputs.append(result)
                check(result['network_disabled'] and result['results']==online,label+': offline_'+mode+'_matches_http')
            check(outputs[0]['pid']!=outputs[1]['pid'],label+': consumer_restore_in_different_process')
            if batch:
                frozen=http(f'/publications/{publication}/api/preview')
                check(frozen['source']['batch_ref']==job['batch_ref'],label+': semantic_business_relation_publication_preserve_batch')
                result=http('/api/batches/'+batch['id']+'?space_id='+space)
                check(len(result['attempts'])==4 and len(result['publications'])==1,label+': explicit_batch_result_chain')
                batch=transition(batch,'disable')
                for values in ({},{'batch_id':batch['id'],'batch_revision':batch['revision']}):
                    http('/api/builds',{'space_id':space,'input_id':registered['id'],**values},409)
                check(True,label+': disabled_batch_and_omission_cannot_build')
                check(http(f'/publications/{publication}/api/objects')==online['objects'] and http(f'/publications/{publication}/offline.zip',binary=True)==raw,label+': disable_preserves_publication_and_package')
                batch=transition(batch,'restore')
                check(batch['state']=='sealed' and len(http('/api/batches/'+batch['id']+'?space_id='+space)['batch']['history'])==5,label+': restore_retains_members_and_history')
                http('/api/builds',{'space_id':space,'input_id':registered['id'],'batch_id':batch['id'],'batch_revision':2},409)
                check(True,label+': stale_pre_disable_admission_rejected')
            # A newly reviewed but unpublished selection must never borrow this old release.
            anchor=http('/candidates/'+candidate+'/api/anchor?point_index=0');changed=[r|{'note':r['note']+' · 新候选'} if i==0 else r for i,r in enumerate(relations)]
            update=http('/api/relation-candidates',body|{'base_candidate_id':candidate,'base_manifest_sha256':anchor['model_manifest_sha256'],'relations':changed},201)['id']
            review(space,update,1);unpublished=http('/api/workflow?space_id='+space)
            check(unpublished['publication_ref'] is None and unpublished['next_stage']=='delivery',label+': newer_selection_does_not_borrow_old_release')
            check(http(f'/publications/{publication}/api/objects')==online['objects'],label+': old_publication_unchanged_after_update')
            # Keep the working demonstration on its published candidate using a fresh review.
            review(space,candidate,2)
            check(http('/api/workflow?space_id='+space)['publication_ref']['publication_id']==publication,label+': explicit_return_to_fixed_candidate')
            (sample_dir/'workflow.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            samples.append({'sample':label,'space_id':space,'input_id':registered['id'],'geometry_candidate':geometry,'semantic_candidate':semantic,'business_candidate':business,
                            'candidate_id':candidate,'publication_id':publication,'offline_bytes':len(raw),'package_sha256':sha(raw),'consumer_pids':[r['pid'] for r in outputs],
                            **({'batch_id':batch['id'],'batch_revision':batch['revision'],'batch_ref':job['batch_ref']} if batch else {})})
        foreign_report=http('/api/workflow?space_id='+foreign['id']);check(foreign_report['candidate_ref'] is None and foreign_report['counts']['input']==0,'foreign_space_remains_empty')
        check(inventory(Path('var/nyu'))==original,'original_runtime_files_unchanged')
        report={'profile':'cospace.preview-batch-acceptance/0.1' if args.with_batches else PROFILE,'status':'passed','checks':checks,'passed':len(checks),'samples':samples,
                'project_id':project['id'],'foreign_space_id':foreign['id'],'original_runtime_files_unchanged':len(original),
                'transport':'real_loopback_HTTP','consumer_network_disabled':True,'scope':'reference_flow_engineering_acceptance',
                'production_ready':False,'robot_ready':False,'quality':'unverified'}
        (output/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
    finally:
        server.terminate()
        try:server.wait(timeout=15)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        log.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);parser.add_argument('--base',type=Path,default=Path('var/nyu/office-0001a-flow-001'))
    parser.add_argument('--sources-config',type=Path,default=Path('deploy/config/preview-sources.json'));parser.add_argument('--serve',action='store_true');parser.add_argument('--port',type=int,default=8768);parser.add_argument('--consumer-request',type=Path)
    parser.add_argument('--with-batches',action='store_true',help='Include acquisition batch lifecycle and admission checks')
    args=parser.parse_args()
    if args.consumer_request:consumer_child(args.consumer_request);return
    if args.output is None:parser.error('--output is required')
    if args.serve:
        if not (args.output/'runtime').is_dir():parser.error('existing isolated runtime required for --serve')
        import uvicorn
        uvicorn.run(app_at(args.output,args.base,args.sources_config),host='127.0.0.1',port=args.port)
    else:run(args)

if __name__=='__main__':main()
