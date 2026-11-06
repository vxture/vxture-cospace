"""P2: real loopback HTTP failure -> idempotent retry -> successful same-source build.

Only this exclusive verification server substitutes a worker that exits 23 when
its one-shot marker is armed. Production code has no fault injection switch.
Original source files and existing workbench runtimes are never modified.
"""
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


def serve(output,port):
    import uvicorn
    app=app_at(output,Path('var/nyu/office-0001a-flow-001'),Path('deploy/config/preview-sources.json'))
    real_popen=subprocess.Popen
    marker=output/'fail-next-worker'
    def worker(command,*args,**kwargs):
        if marker.is_file() and len(command)>2 and command[2]=='experiments.scripts.build_nyu_flow_preview':
            marker.unlink()
            command=[sys.executable,'-c','print("P2 controlled worker failure; source unchanged",flush=True);raise SystemExit(23)']
        return real_popen(command,*args,**kwargs)
    # Scoped to this verification subprocess, not the authorized demo server.
    subprocess.Popen=worker
    uvicorn.run(app,host='127.0.0.1',port=port,access_log=False)


def run(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    original=inventory(Path('var/nyu'));checks=[]
    def save(name,value):(output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('original-before.json',original)
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    opener=build_opener(ProxyHandler({}))
    def http(path,body=None,status=200,binary=False):
        data=None if body is None else json.dumps(body).encode()
        try:
            with opener.open(Request(origin+path,data=data,headers={'Content-Type':'application/json'}),timeout=45) as response:code=response.status;raw=response.read()
        except HTTPError as e:code=e.code;raw=e.read()
        assert code in (status if isinstance(status,tuple) else (status,)),(path,code,raw[:500]);return raw if binary else json.loads(raw)
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    def wait(identity,space):
        deadline=time.monotonic()+135
        while time.monotonic()<deadline:
            job=next(j for j in http('/api/builds?space_id='+space)['jobs'] if j['id']==identity)
            if job['state'] not in ('queued','running'):return job
            time.sleep(.25)
        raise TimeoutError('worker_timeout')
    with (output/'server.log').open('wb') as log:
        server=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.verify_build_recovery','--serve','--output',str(output),'--port',str(port)],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError('server_exited')
                try:http('/api/projects');break
                except URLError:time.sleep(.1)
            project=http('/api/projects',{'name':'P2 失败恢复验收 · 独立本地样本'},201)
            space=http('/api/spaces',{'name':'NYU 办公室 · 失败恢复','project_id':project['id']},201)['id']
            other=http('/api/spaces',{'name':'跨场景负例','project_id':project['id']},201)['id']
            entry=http('/api/inputs',{'space_id':space,'source_id':'nyu-office-short','label':'未修改的 NYU 原资料'},201)['input']
            batch=http('/api/batches',{'space_id':space,'name':'P2 封存资料','origin':'imported_sample','note':'流程验证，精度未验收'},201)
            def change_batch(record,op,**values):return http('/api/batches/'+record['id']+'/transitions',{'space_id':space,'expected_revision':record['revision'],'operation':op,'reason':'P2 验收',**values})
            batch=change_batch(batch,'replace_members',input_ids=[entry['id']]);batch=change_batch(batch,'seal')
            start={'space_id':space,'input_id':entry['id'],'batch_id':batch['id'],'batch_revision':batch['revision']}
            first=wait(http('/api/builds',start,202)['id'],space);check(first['state']=='succeeded','initial_real_build_succeeded')
            body={'space_id':space,'candidate_id':first['id'],'expected_revision':0}
            comparison=http('/api/candidate-comparisons',body)
            http('/api/candidate-reviews',body|{'comparison_sha256':comparison['comparison_sha256'],'acknowledge_unverified':True,'note':'P2 固定历史发布，非质量验收'})
            publication=http('/api/publications',body|{'expected_revision':1},201)
            old_bundle=http(publication['preview_url']+'offline.zip',binary=True)
            (output/'fail-next-worker').write_text('controlled exit 23',encoding='utf-8')
            failed=wait(http('/api/builds',start,202)['id'],space);save('failed-job.json',failed)
            check(failed['state']=='failed' and failed['error']=='build_failed','real_worker_exit_23_recorded_as_failure')
            failed_path=output/'runtime/preview-builds'/failed['id']/'job.json';failed_raw=failed_path.read_bytes()
            token='a'*32;retry={'space_id':space,'retry_of':failed['id'],'request_id':token}
            http('/api/build-retries',retry|{'space_id':other},409);check(True,'cross_scene_retry_rejected')
            with ThreadPoolExecutor(2) as pool:
                responses=list(pool.map(lambda _:http('/api/build-retries',retry,status=(200,202)),range(2)))
            # First request admitted; response-loss replay reuses the same persistent token.
            check(sorted(r['created'] for r in responses)==[False,True] and len({r['job']['id'] for r in responses})==1,'concurrent_same_request_creates_one_task')
            admitted=next(r for r in responses if r['created']);replay=http('/api/build-retries',retry)
            check(admitted['created'] and not replay['created'] and admitted['job']['id']==replay['job']['id'],'same_request_replay_reuses_one_task')
            recovered=wait(admitted['job']['id'],space);save('recovered-job.json',recovered)
            check(recovered['state']=='succeeded','retry_real_model_and_dual_views_succeeded')
            check(recovered['retry_of']==failed['id'] and recovered['input_binding']==failed['input_binding'] and recovered['batch_ref']==failed['batch_ref'],'retry_preserves_original_input_and_batch')
            check(failed_path.read_bytes()==failed_raw,'original_failed_record_unchanged')
            again=http('/api/build-retries',retry)
            check(not again['created'] and again['job']['id']==recovered['id'],'completed_retry_replay_still_reuses_task')
            model=http('/candidates/'+recovered['id']+'/api/preview')
            check(all(model[k]['source_model_sha256']==model['members']['spatial.npz']['sha256'] for k in ('human_view','agent_view')),'recovered_dual_views_share_model')
            check(http(publication['preview_url']+'offline.zip',binary=True)==old_bundle,'historical_publication_still_readable_and_unchanged')
            disabled=change_batch(batch,'disable')
            http('/api/build-retries',retry|{'request_id':'b'*32},409)
            check(len([j for j in http('/api/builds?space_id='+space)['jobs'] if j.get('retry_of')==failed['id']])==1,'changed_batch_blocks_new_retry')
            # Explicit test restoration retains a new revision; original retry must not adopt it.
            restored=change_batch(disabled,'restore')
            http('/api/build-retries',retry|{'request_id':'c'*32},409);check(True,'restored_batch_does_not_silently_replace_admitted_revision')
            (output/'fail-next-worker').write_text('controlled exit 23 for browser acceptance',encoding='utf-8')
            ui_failed=wait(http('/api/builds',start|{'batch_revision':restored['revision']},202)['id'],space)
            check(ui_failed['state']=='failed','browser_acceptance_failure_has_current_admitted_batch')
            check(http('/api/selection?space_id='+space)['candidate_id']==first['id'],'retry_never_silently_selects_new_candidate')
            check(inventory(Path('var/nyu'))==original,'original_195_records_unchanged')
            save('acceptance.json',{'profile':'cospace.build-recovery-verification/0.1','status':'passed','passed':len(checks),'checks':checks,
                'runtime':str(output/'runtime'),'space_id':space,'input_id':entry['id'],'candidate_id':first['id'],
                'failed_id':failed['id'],'recovered_id':recovered['id'],'publication_id':publication['id'],
                'ui_failed_id':ui_failed['id'],
                'source_model_sha256':model['members']['spatial.npz']['sha256'],'quality':'unverified','robot_ready':False,'production_ready':False,
                'failure_injection':'one_worker_exits_23_in_exclusive_verification_server','original_records_unchanged':len(original)})
            print(json.dumps({'status':'passed','passed':len(checks),'space_id':space,'failed_id':failed['id'],'recovered_id':recovered['id']},ensure_ascii=False))
        finally:
            server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--serve',action='store_true');parser.add_argument('--port',type=int,default=8771)
    args=parser.parse_args()
    if args.serve:serve(args.output.resolve(),args.port)
    else:run(args.output)
