"""One real NYU scene: registration -> model -> two views -> fixed preview.

Exclusive local runtime; no writes to original datasets, records or platform policies.
The isolated engineering HTTP server is stopped after verification.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
import numpy as np
from experiments.scripts.verify_preview_workflow import app_at,inventory
from packages.construction.preview_model import PreviewModel,surface_cells,digest
from packages.data.nyu_rgbd import ply_bytes
from packages.views.agent.preview_offline import OfflinePreview,sha


def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    original=inventory(Path('var/nyu'))
    (output/'original-before.json').write_text(json.dumps(original,indent=2)+'\n',encoding='utf-8')
    base=Path('var/nyu/office-0001a-flow-001');config=Path('deploy/config/preview-sources.json')
    app_at(output,base,config)
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    with (output/'server.log').open('wb') as log:
        server=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.verify_preview_workflow',
            '--serve','--output',str(output),'--base',str(base),'--sources-config',str(config),'--port',str(port)],
            stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        checks=[];origin=f'http://127.0.0.1:{port}'
        def http(path,body=None,status=200,binary=False):
            data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
            try:
                with urlopen(Request(origin+path,data=data,headers={'Content-Type':'application/json'}),timeout=45) as response:code=response.status;raw=response.read()
            except HTTPError as error:code=error.code;raw=error.read()
            assert code==status,(path,code,raw[:500])
            return raw if binary else json.loads(raw)
        def check(value,name):
            if not value:raise AssertionError(name)
            checks.append(name)
        def save(name,value):(output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError('verification_server_exited')
                try:http('/api/projects');break
                except URLError:time.sleep(.1)
            else:raise TimeoutError('verification_server_start_timeout')
            project=http('/api/projects',{'name':'独立场景空间构建验证 · 本地工程环境'},201)
            space=http('/api/spaces',{'name':'NYU 办公室 · 短场景构建验证','project_id':project['id'],
                'description':'office_0001a 的短序列样本；唯一物理场景；精度未验收'},201)['id']
            other=http('/api/spaces',{'name':'隔离负例 · 无资料','project_id':project['id']},201)['id']
            entry=http('/api/inputs',{'space_id':space,'source_id':'nyu-office-short','label':'NYU office_0001a · RGB-D 与已有估计轨迹'},201)['input']
            repeated=http('/api/inputs',{'space_id':space,'source_id':'nyu-office-short','label':'重复登记'})
            check(not repeated['created'] and repeated['input']['id']==entry['id'],'same_scene_same_source_reuses_input')
            preflight=http('/api/inputs/'+entry['id']+'/preflight',{});save('input-preflight.json',preflight)
            check(preflight['status']=='passed','real_source_integrity_preflight')
            http('/api/builds',{'space_id':other,'input_id':entry['id']},409);check(True,'cross_scene_build_rejected')
            job=http('/api/builds',{'space_id':space,'input_id':entry['id']},202);identity=job['id']
            deadline=time.monotonic()+135
            while job['state'] in ('queued','running'):
                if time.monotonic()>deadline:raise TimeoutError('real_construction_timeout')
                time.sleep(.25);job=next(j for j in http('/api/builds?space_id='+space)['jobs'] if j['id']==identity)
            check(job['state']=='succeeded','real_build_subprocess_completed');save('build-job.json',job)
            root=output/'runtime/preview-builds'/identity/'output';model=PreviewModel(root);manifest=model.manifest
            save('model-manifest.json',manifest)
            check(manifest['space_id']==space and manifest['source']['input_binding']['id']==entry['id'],'model_preserves_scene_and_input')
            check(http('/api/selection?space_id='+space)['candidate_id'] is None,'build_does_not_silently_select')
            check([e['stage'] for e in manifest['events']]==['source_verified','candidate_built','human_view_derived','agent_view_derived'],'ordered_model_then_dual_view_stages')
            with np.load(root/'spatial.npz',allow_pickle=False) as canonical:
                points=canonical['points'];colors=canonical['colors']
            check((root/'human.ply').read_bytes()==ply_bytes(points,colors,np.ones(len(points),bool)),'human_view_matches_frozen_geometry_and_color')
            expected=surface_cells(points,manifest['agent_view']['resolution_m'])
            with np.load(root/'agent.npz',allow_pickle=False) as agent:
                check(np.array_equal(agent['cells'],expected),'agent_view_matches_canonical_surface_voxelization')
            canonical_sha=digest(root/'spatial.npz')
            check(all(manifest[k]['source_model_sha256']==canonical_sha for k in ('human_view','agent_view')),'dual_views_share_exact_geometry_digest')
            check(all((root/name).stat().st_size==m['bytes'] and digest(root/name)==m['sha256'] for name,m in manifest['members'].items()),'all_artifact_sizes_and_digests_match')
            point=((expected[0]+.5)*model.resolution).tolist();unknown=(points.max(axis=0)+10).tolist()
            check(model.query(point)['state']=='surface_candidate' and model.query(unknown)['state']=='unknown','unknown_is_never_inferred_free')
            body={'space_id':space,'candidate_id':identity,'expected_revision':0}
            comparison=http('/api/candidate-comparisons',body)
            http('/api/candidate-reviews',body|{'comparison_sha256':comparison['comparison_sha256'],'acknowledge_unverified':True,
                'note':'自动工程流程核对：仅验证资料、几何与双视图引用，非质量验收或正式交付'})
            publication=http('/api/publications',body|{'expected_revision':1},201);save('fixed-publication.json',publication)
            check(publication['candidate_id']==identity and publication['space_id']==space,'fixed_preview_binds_exact_scene_and_candidate')
            check('semantic_annotation' not in manifest and publication['quality']=='unverified','geometric_workflow_does_not_require_invented_semantics')
            info=http(publication['preview_url']+'offline.json');raw=http(publication['preview_url']+'offline.zip',binary=True)
            (output/'offline.zip').write_bytes(raw);check(sha(raw)==info['sha256'],'offline_bundle_integrity')
            offline=OfflinePreview(raw,publication['id'],sha(raw))
            online={}
            for key,p in [('surface',point),('unknown',unknown)]:
                online[key]=http(publication['query_url'],{'point_m':p})
                check(online[key]==offline.query(p),key+'_online_offline_equal')
            check(not online['surface']['robot_ready'] and not manifest['real_release_ready'],'quality_and_robot_readiness_not_inferred')
            check(http('/api/inputs?space_id='+other)['inputs']==[],'unrelated_scene_remains_empty')
            check(inventory(Path('var/nyu'))==original,'original_engineering_records_unchanged')
            report={'profile':'cospace.scene-construction-verification/0.1','status':'passed','passed':len(checks),'checks':checks,
                'space_id':space,'input_id':entry['id'],'candidate_id':identity,'publication_id':publication['id'],
                'source_id':'nyu-office-short','runtime':str(output/'runtime'),'source_model_sha256':canonical_sha,
                'model_points':len(points),'surface_cells':len(expected),'used_frames':manifest['construction']['used_frames'],
                'input_frames':manifest['construction']['input_frames'],
                'artifacts':{name:manifest['members'][name] for name in ('spatial.npz','human.ply','agent.npz')},
                'offline_bytes':len(raw),'offline_sha256':sha(raw),'original_records_unchanged':len(original),
                'quality':'unverified','production_ready':False,'robot_ready':False,'semantic_objects_added':0,
                'execution':'real_loopback_HTTP_and_build_subprocess','stage_execution':'one_task_sequential_model_then_views',
                'scope':'isolated_short_scene_workflow_not_complete_scene_or_accuracy_acceptance'}
            save('acceptance.json',report);save('query-checks.json',online)
            print(json.dumps(report,ensure_ascii=False),flush=True)
            return report
        finally:
            server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
