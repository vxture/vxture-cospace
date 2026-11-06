"""P3 real HTTP/model/view workers, exclusive runtime and one-shot view faults."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener,ProxyHandler
from experiments.scripts.verify_preview_workflow import app_at,inventory
from packages.construction.preview_model import digest


def serve(output,port):
    import uvicorn
    app=app_at(output,Path('var/nyu/office-0001a-flow-001'),Path('deploy/config/preview-sources.json'))
    real_popen=subprocess.Popen
    def launch(command,*args,**kwargs):
        if len(command)>2 and command[2]=='experiments.scripts.derive_frozen_preview':
            task=json.loads(Path(command[command.index('--task')+1]).read_bytes());marker=output/('fail-next-'+task['view_kind'])
            if marker.is_file():
                marker.unlink();command=[sys.executable,'-c','print("P3 controlled view worker exit 23",flush=True);raise SystemExit(23)']
        return real_popen(command,*args,**kwargs)
    subprocess.Popen=launch
    uvicorn.run(app,host='127.0.0.1',port=port,access_log=False)


def run(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False);original=inventory(Path('var/nyu'));checks=[]
    def save(name,value):(output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('original-before.json',original)
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    origin=f'http://127.0.0.1:{port}';opener=build_opener(ProxyHandler({}))
    def http(path,body=None,status=200,binary=False):
        data=None if body is None else json.dumps(body).encode()
        try:
            with opener.open(Request(origin+path,data=data,headers={'Content-Type':'application/json'}),timeout=45) as response:code=response.status;raw=response.read()
        except HTTPError as e:code=e.code;raw=e.read()
        assert code in (status if isinstance(status,tuple) else (status,)),(path,code,raw[:700]);return raw if binary else json.loads(raw)
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    def wait(identity,space):
        deadline=time.monotonic()+140
        while time.monotonic()<deadline:
            job=next(j for j in http('/api/builds?space_id='+space)['jobs'] if j['id']==identity)
            if job['state'] not in ('queued','running'):return job
            time.sleep(.2)
        raise TimeoutError('split_build_timeout')
    def stages(job,space):return http('/api/build-stages?space_id='+space+'&candidate_id='+job)
    def retry(space,job,kind,token):return http('/api/view-derivations',{'space_id':space,'candidate_id':job,'view_kind':kind,'request_id':token},(200,202))
    with (output/'server.log').open('wb') as log:
        server=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.verify_split_views','--serve','--output',str(output),'--port',str(port)],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError('server_exited')
                try:http('/api/projects');break
                except URLError:time.sleep(.1)
            project=http('/api/projects',{'name':'P3 模型与视图独立派生 · 本地验收'},201)
            space=http('/api/spaces',{'name':'NYU 办公室 · 分阶段构建','project_id':project['id']},201)['id']
            other=http('/api/spaces',{'name':'跨场景拒绝','project_id':project['id']},201)['id']
            entry=http('/api/inputs',{'space_id':space,'source_id':'nyu-office-short','label':'NYU 未修改样本'},201)['input']
            start={'space_id':space,'input_id':entry['id']}
            (output/'fail-next-human').write_text('controlled view exit 23')
            initial=wait(http('/api/builds',start,202)['id'],space);a=stages(initial['id'],space);save('initial-stages.json',a)
            check(initial['state']=='views_failed' and a['views']['human']['state']=='failed' and a['views']['agent']['state']=='succeeded','human_real_worker_failed_after_model_frozen')
            check(not a['candidate_ready'] and a['frozen_model'] is not None,'model_complete_is_distinct_from_candidate_ready')
            http('/api/selection',{'space_id':space,'candidate_id':initial['id'],'expected_revision':0},409);check(True,'incomplete_views_cannot_select_for_publication')
            model_root=output/'runtime/preview-builds'/initial['id']/'frozen';frozen_bytes={p.name:p.read_bytes() for p in model_root.iterdir()}
            agent_ref=initial['view_tasks']['agent'];agent_root=output/'runtime/preview-builds'/agent_ref['job_id']/'views'/agent_ref['task_id'];agent_bytes={str(p.relative_to(agent_root)):p.read_bytes() for p in agent_root.rglob('*') if p.is_file()}
            first_bytes=(output/'runtime/preview-builds'/initial['id']/'job.json').read_bytes()
            with ThreadPoolExecutor(2) as pool:responses=list(pool.map(lambda _:retry(space,initial['id'],'human','a'*32),range(2)))
            check(sorted(r['created'] for r in responses)==[False,True] and len({r['job']['id'] for r in responses})==1,'concurrent_view_submission_creates_one_candidate')
            human=wait(responses[0]['job']['id'],space);b=stages(human['id'],space)
            check(human['state']=='succeeded' and b['candidate_ready'],'human_only_retry_completes_candidate')
            check(human['frozen_model']==initial['frozen_model'] and human['view_tasks']['agent']==agent_ref,'human_retry_reuses_exact_model_and_agent_task')
            check(all((agent_root/name).read_bytes()==raw for name,raw in agent_bytes.items()),'other_view_task_and_files_unchanged')
            check((output/'runtime/preview-builds'/initial['id']/'job.json').read_bytes()==first_bytes,'original_failed_view_job_unchanged')
            manifest=http('/candidates/'+human['id']+'/api/preview');save('composed-model.json',manifest)
            check(manifest['derivation']['frozen_model']==initial['frozen_model'] and manifest['derivation']['views']['human']['id']==human['view_tasks']['human']['task_id'],'candidate_pins_exact_model_and_two_view_tasks')
            body={'space_id':space,'candidate_id':human['id'],'expected_revision':0};comparison=http('/api/candidate-comparisons',body)
            http('/api/candidate-reviews',body|{'comparison_sha256':comparison['comparison_sha256'],'acknowledge_unverified':True,'note':'P3 固定组合与视图来源核对，不代表精度验收'})
            publication=http('/api/publications',body|{'expected_revision':1},201);old_zip=http(publication['preview_url']+'offline.zip',binary=True)
            check(publication['derivation']==manifest['derivation'],'publication_pins_model_and_view_composition')
            (output/'fail-next-agent').write_text('controlled view exit 23')
            agent_failed=wait(retry(space,human['id'],'agent','b'*32)['job']['id'],space);c=stages(agent_failed['id'],space)
            check(agent_failed['state']=='views_failed' and c['views']['agent']['state']=='failed' and c['views']['human']['state']=='succeeded','agent_real_worker_failure_preserves_human')
            agent=wait(retry(space,agent_failed['id'],'agent','c'*32)['job']['id'],space)
            check(agent['state']=='succeeded' and agent['view_tasks']['human']==human['view_tasks']['human'],'agent_only_retry_completes_with_original_human')
            check(all((model_root/name).read_bytes()==raw for name,raw in frozen_bytes.items()),'frozen_model_manifest_and_geometry_never_rewritten')
            rederived=wait(retry(space,agent['id'],'human','d'*32)['job']['id'],space)
            check(rederived['state']=='succeeded' and rederived['view_tasks']['human']!=agent['view_tasks']['human'] and rederived['frozen_model']==agent['frozen_model'],'same_model_supports_new_successful_view_version')
            current=http('/candidates/'+rederived['id']+'/api/preview')
            check(all(current[k]['source_model_sha256']==current['members']['spatial.npz']['sha256'] for k in ('human_view','agent_view')),'all_new_view_versions_share_frozen_geometry_digest')
            http('/api/view-derivations',{'space_id':other,'candidate_id':rederived['id'],'view_kind':'human','request_id':'e'*32},409);check(True,'cross_scene_view_derivation_rejected')
            check(http('/api/selection?space_id='+space)['candidate_id']==human['id'],'view_reruns_never_auto_select_or_publish')
            check(http(publication['preview_url']+'offline.zip',binary=True)==old_zip,'historical_fixed_release_and_offline_bundle_unchanged')
            # Genuine failed task ready for browser recovery with the normal server.
            (output/'fail-next-agent').write_text('controlled view exit 23 for browser')
            ui_failed=wait(retry(space,rederived['id'],'agent','f'*32)['job']['id'],space)
            check(ui_failed['state']=='views_failed','browser_failure_fixture_has_frozen_model_and_successful_counterpart')
            check(inventory(Path('var/nyu'))==original,'original_195_records_unchanged')
            report={'profile':'cospace.split-view-verification/0.1','status':'passed','passed':len(checks),'checks':checks,'runtime':str(output/'runtime'),
                'space_id':space,'input_id':entry['id'],'candidate_id':human['id'],'publication_id':publication['id'],'frozen_job_id':initial['id'],
                'ui_failed_id':ui_failed['id'],'latest_candidate_id':rederived['id'],'source_model_sha256':current['members']['spatial.npz']['sha256'],
                'quality':'unverified','production_ready':False,'robot_ready':False,'original_records_unchanged':len(original),
                'failure_injection':'only_selected_view_worker_exits_23_in_exclusive_verification_server'}
            save('acceptance.json',report);print(json.dumps(report,ensure_ascii=False))
        finally:
            server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--serve',action='store_true');parser.add_argument('--port',type=int,default=8772)
    args=parser.parse_args()
    if args.serve:serve(args.output.resolve(),args.port)
    else:run(args.output)
