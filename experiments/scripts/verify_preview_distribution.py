"""Pause and restore fixed publications in an exclusive copy of an existing sample runtime."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from jsonschema import Draft202012Validator,FormatChecker
from experiments.scripts.verify_preview_workflow import inventory
from packages.views.agent.preview_offline import OfflinePreview,sha

def run(args):
    source=args.source.resolve();output=args.output.resolve();seed=json.loads((source/'acceptance.json').read_bytes())
    if seed.get('profile') not in ('cospace.preview-control-acceptance/0.1','cospace.preview-batch-acceptance/0.1'):raise ValueError('existing_sample_runtime_required')
    original=inventory(Path('var/nyu'));source_before=inventory(source/'runtime')
    output.mkdir(parents=True,exist_ok=False);shutil.copytree(source/'runtime',output/'runtime')
    (output/'original-before.json').write_text(json.dumps(original,indent=2)+'\n',encoding='utf-8')
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    log=(output/'server.log').open('wb');server=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.verify_preview_workflow','--serve','--output',str(output),'--port',str(port)],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    origin=f'http://127.0.0.1:{port}';checks=[];samples=[]
    validator=Draft202012Validator(json.loads(Path('contracts/schemas/preview-artifact-control-v0.1.schema.json').read_bytes()),format_checker=FormatChecker())
    def http(path,body=None,expected=200,binary=False,headers=None,method=None):
        try:
            with urlopen(Request(origin+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json',**(headers or {})},method=method),timeout=45) as response:status=response.status;raw=response.read();cache=response.headers.get('Cache-Control')
        except HTTPError as e:status=e.code;raw=e.read();cache=e.headers.get('Cache-Control')
        assert status==expected,(path,status,raw[:500])
        if path.startswith('/publications/'):assert cache=='no-store',(path,cache)
        return raw if binary else json.loads(raw)
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    def report(space,key):
        result=http('/api/artifact-control?space_id='+space+'&artifact='+key);validator.validate(result);return result
    def change(current,op,expected=200):return http('/api/artifact-control/transitions',{'space_id':current['space_id'],'artifact':current['artifact'],'expected_revision':current['record']['revision'],'expected_snapshot_sha256':current['snapshot_sha256'],'operation':op,'reason':'固定发布分发隔离流程验证'},expected)
    try:
        for _ in range(100):
            if server.poll() is not None:raise RuntimeError('isolated_server_exited')
            try:http('/api/projects');break
            except URLError:time.sleep(.1)
        else:raise RuntimeError('isolated_server_timeout')
        for sample in seed['samples']:
            label=sample['sample'];space=sample['space_id'];pub=sample['publication_id'];key='publication:'+pub;prefix='/publications/'+pub+'/';print(label+': baseline → pause every route → held offline consumer → restore',flush=True)
            first=report(space,key);check(first['record']['revision']==0 and first['publication_control_supported'],label+': default_distribution_active')
            selection=http('/api/selection?space_id='+space);record=http(prefix+'publication.json');manifest=http(prefix+'model.json')
            obj=http(prefix+'api/objects');point=obj['objects'][0]['anchor_m'];r=manifest['agent_view']['resolution_m'];bounds=[[v-r for v in point],[v+r for v in point]]
            bodies={'api/query':{'point_m':point},'api/query-range':{'bounds_m':bounds,'frame_id':manifest['frame_id'],'limit':1024}}
            names=['','api/preview','api/objects','api/objects/'+obj['objects'][0]['object_id'],'api/checklist','api/lineage','offline.zip','offline.json',*record['files'],'publication.json',*bodies]
            names=list(dict.fromkeys(names));baseline={name:http(prefix+name,bodies.get(name),binary=True) for name in names}
            bundle=baseline['offline.zip'];offline=OfflinePreview(bundle,pub,sha(bundle));check(offline.objects()==obj,label+': held_package_matches_online_before_pause')
            before_files={p.name:sha(p.read_bytes()) for p in (output/'runtime/preview-builds/publications'/pub).iterdir() if p.is_file()}
            paused=change(first,'pause_distribution');check(paused['lifecycle_state']=='paused' and paused['revision']==1,label+': pause_with_reason_history')
            change(first,'pause_distribution',409);check(True,label+': stale_revision_rejected')
            for name in names:
                rejected=http(prefix+name,bodies.get(name),409)
                check(rejected['detail']=='publication_distribution_paused',label+': denied '+(name or 'HTML'))
            check(http(prefix+'agent.npz',expected=409,headers={'Range':'bytes=0-10'})['detail']=='publication_distribution_paused',label+': range_request_denied')
            check(http(prefix+'model.json',expected=409,headers={'If-None-Match':'"previous-etag"'})['detail']=='publication_distribution_paused',label+': conditional_request_denied')
            http(prefix+'offline.zip',expected=409,binary=True,method='HEAD');check(True,label+': head_request_denied')
            http(prefix.rstrip('/'),expected=409);check(True,label+': slashless_entry_denied')
            state=http('/api/spaces/'+space);check(state['publication_id'] is None and state['state']=='distribution_paused',label+': default_space_entry_not_replaced')
            listing=http('/api/publications?space_id='+space)['publications'];metadata=next(p for p in listing if p['id']==pub)
            check(metadata['lifecycle_state']=='paused' and 'files' not in metadata and 'selection_review' not in metadata,label+': management_metadata_retained_without_contents')
            http('/api/publication-comparisons',{'space_id':space,'base_publication_id':pub,'target_publication_id':pub},409);check(True,label+': comparison_route_denied')
            stages={s['id']:s for s in http('/api/workflow?space_id='+space)['stages']};check(stages['delivery']['status']==stages['space']['status']=='blocked' and stages['space']['action']['module']=='delivery',label+': workflow_links_to_management')
            catalog=http('/api/artifacts?space_id='+space);check(all(i['lifecycle_state']=='paused' and not i['resources'] for i in catalog['items'] if i['record_id']==pub),label+': catalog_retains_paused_history')
            check(offline.objects()==obj and offline.query(point)==json.loads(baseline['api/query']),label+': already_held_offline_package_keeps_working')
            # Independent consumer processes install and restore the held bytes with network disabled.
            consumer_dir=output/label;consumer_dir.mkdir();zip_path=consumer_dir/'held.zip';zip_path.write_bytes(bundle);outputs=[]
            for mode in ('install','restore'):
                request={'consumer':str(consumer_dir/'consumer'),'space':space,'publication':pub,'sha256':sha(bundle),'mode':mode,'bundle':str(zip_path),'point':point,'bounds':bounds,'frame_id':manifest['frame_id'],'result':str(consumer_dir/(mode+'-result.json'))}
                request_path=consumer_dir/(mode+'-request.json');request_path.write_text(json.dumps(request),encoding='utf-8')
                if mode=='restore':zip_path.unlink()
                subprocess.run([sys.executable,'-X','utf8','-m','experiments.scripts.verify_preview_workflow','--consumer-request',str(request_path)],check=True,timeout=30,capture_output=True)
                outputs.append(json.loads(Path(request['result']).read_bytes()))
            check(outputs[0]['pid']!=outputs[1]['pid'] and all(o['network_disabled'] and o['results']['objects']==obj for o in outputs),label+': held_offline_cross_process_restore_while_paused')
            restored=change(report(space,key),'restore');check(restored['lifecycle_state']=='active' and restored['revision']==2,label+': restored_same_fixed_publication')
            for name in names:
                value=http(prefix+name,bodies.get(name),binary=True)
                if name not in ('api/checklist','api/lineage'):check(value==baseline[name],label+': restored exact '+(name or 'HTML'))
            check(http('/api/selection?space_id='+space)==selection,label+': selection_unchanged')
            check(http('/api/spaces/'+space)['publication_id']==pub,label+': default_entry_returns_after_restore')
            after_files={p.name:sha(p.read_bytes()) for p in (output/'runtime/preview-builds/publications'/pub).iterdir() if p.is_file()};check(before_files==after_files,label+': fixed_snapshot_files_unchanged')
            final=report(space,key);(output/(label+'-distribution.json')).write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            samples.append({**sample,'distribution_revision':final['record']['revision'],'distribution_paths':len(names),'package_sha256':sha(bundle),'offline_consumer_pids':[o['pid'] for o in outputs]})
        check(inventory(Path('var/nyu'))==original,'original_managed_files_unchanged');check(inventory(source/'runtime')==source_before,'source_runtime_unchanged')
        result={'profile':'cospace.preview-distribution-acceptance/0.1','passed':len(checks),'checks':checks,'samples':samples,'original_managed_files_unchanged':len(original),'source_files_unchanged':len(source_before),'transport':'real_loopback_HTTP','publication_control_supported':True,'quality':'unverified','robot_ready':False}
        (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        log.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);run(parser.parse_args())
if __name__=='__main__':main()
