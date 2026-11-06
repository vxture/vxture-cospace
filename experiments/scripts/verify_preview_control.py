"""Exercise controlled lifecycle mutations over an exclusive copy of an H1 sample runtime."""
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

def run(args):
    source=args.source.resolve();output=args.output.resolve()
    seed=json.loads((source/'acceptance.json').read_bytes())
    if seed.get('profile')!='cospace.preview-batch-acceptance/0.1':raise ValueError('H1_batch_runtime_required')
    original=inventory(Path('var/nyu'));source_before=inventory(source/'runtime')
    output.mkdir(parents=True,exist_ok=False);shutil.copytree(source/'runtime',output/'runtime')
    (output/'original-before.json').write_text(json.dumps(original,indent=2)+'\n',encoding='utf-8')
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    log=(output/'server.log').open('wb');server=subprocess.Popen([sys.executable,'-X','utf8','-m','experiments.scripts.verify_preview_workflow','--serve','--output',str(output),'--port',str(port)],stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    origin=f'http://127.0.0.1:{port}';checks=[];samples=[]
    validator=Draft202012Validator(json.loads(Path('contracts/schemas/preview-artifact-control-v0.1.schema.json').read_bytes()),format_checker=FormatChecker())
    def http(path,body=None,expected=200,binary=False):
        try:
            with urlopen(Request(origin+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'}),timeout=45) as response:status=response.status;raw=response.read()
        except HTTPError as e:status=e.code;raw=e.read()
        assert status==expected,(path,status,raw[:500])
        return raw if binary else json.loads(raw)
    def check(value,label):
        if not value:raise AssertionError(label)
        checks.append(label)
    def report(space,key):
        result=http('/api/artifact-control?space_id='+space+'&artifact='+key);validator.validate(result);return result
    def body(current,op):return {'space_id':current['space_id'],'artifact':current['artifact'],'expected_revision':current['record']['revision'],'expected_snapshot_sha256':current['snapshot_sha256'],'operation':op,'reason':'生命周期隔离样本流程验证'}
    def change(space,key,op):return http('/api/artifact-control/transitions',body(report(space,key),op))
    try:
        for _ in range(100):
            if server.poll() is not None:raise RuntimeError('isolated_server_exited')
            try:http('/api/projects');break
            except URLError:time.sleep(.1)
        else:raise RuntimeError('isolated_server_timeout')
        before=inventory(output/'runtime')
        for sample in seed['samples']:
            label=sample['sample'];space=sample['space_id'];input_id=sample['input_id'];input_key='input:'+input_id;geometry=sample['geometry_candidate'];candidate_key='candidate:'+geometry;pub=sample['publication_id']
            check(report(space,input_key)['record']['revision']==0,label+': legacy_defaults_active_readonly')
        check(before==inventory(output/'runtime'),'lifecycle_GET_does_not_create_files')
        for sample in seed['samples']:
            label=sample['sample'];print(label+': disable → restore → archive → restore → real build',flush=True)
            space=sample['space_id'];input_id=sample['input_id'];input_key='input:'+input_id;geometry=sample['geometry_candidate'];candidate_key='candidate:'+geometry;pub=sample['publication_id']
            selection=http('/api/selection?space_id='+space);objects=http('/publications/'+pub+'/api/objects');package=http('/publications/'+pub+'/offline.zip',binary=True)
            old=body(report(space,input_key),'disable_input');disabled=http('/api/artifact-control/transitions',old)
            check(disabled['lifecycle_state']=='disabled',label+': input_disabled_with_history')
            http('/api/artifact-control/transitions',old,409);check(True,label+': old_revision_rejected')
            for params in ({},{'batch_id':sample['batch_id'],'batch_revision':sample['batch_revision']}):http('/api/builds',{'space_id':space,'input_id':input_id,**params},409)
            check(True,label+': direct_and_batch_build_blocked')
            check(http('/api/inputs?space_id='+space)['inputs'][0]['lifecycle_state']=='disabled',label+': input_list_shows_disabled')
            http('/api/artifact-control/transitions',body(report(space,'candidate:'+sample['candidate_id']),'archive_candidate'),409)
            check(True,label+': current_candidate_archive_blocked')
            restored=change(space,input_key,'restore');check(restored['revision']==2 and restored['lifecycle_state']=='active',label+': input_restore_repreflights')
            # A fresh batch changes the scope snapshot; stale reports cannot commit.
            stale=body(report(space,input_key),'disable_input')
            batch=http('/api/batches',{'space_id':space,'name':'生命周期草稿验证','origin':'imported_sample','note':'公开样本验证'},201)
            http('/api/artifact-control/transitions',stale,409);check(True,label+': changed_reference_snapshot_rejected')
            batch=http('/api/batches/'+batch['id']+'/transitions',{'space_id':space,'expected_revision':0,'operation':'replace_members','reason':'选择样本','input_ids':[input_id]})
            change(space,input_key,'disable_input')
            http('/api/batches/'+batch['id']+'/transitions',{'space_id':space,'expected_revision':1,'operation':'seal','reason':'应被资料停用阻断'},409);check(True,label+': disabled_member_cannot_seal')
            change(space,input_key,'restore')
            # Disable the extra draft so it no longer prevents input archival independently of the selected candidate.
            http('/api/batches/'+batch['id']+'/transitions',{'space_id':space,'expected_revision':1,'operation':'disable','reason':'保留测试草稿'})
            archived=change(space,candidate_key,'archive_candidate');check(archived['lifecycle_state']=='archived',label+': historical_geometry_archived')
            http('/api/selection',{'space_id':space,'candidate_id':geometry,'expected_revision':selection['revision']},409)
            http('/api/publications',{'space_id':space,'candidate_id':geometry,'expected_revision':selection['revision']},409)
            geometry_report=report(space,candidate_key);model=http('/candidates/'+geometry+'/model.json');rule=http('/api/ontologies')['ontologies'][0]
            semantic={'space_id':space,'base_candidate_id':geometry,'base_manifest_sha256':next(i for i in http('/api/artifacts?space_id='+space)['items'] if i['key']==candidate_key)['model_manifest_sha256'],'ontology_ref':{k:rule[k] for k in ('ontology_id','version','sha256')},'objects':[{'object_id':'lifecycle-test','type_id':'room','properties':{'name':'测试待核实'},'point_index':0}]}
            http('/api/semantic-candidates',semantic,409);check(True,label+': archived_geometry_new_select_derive_publish_blocked')
            check(http('/api/selection?space_id='+space)==selection,label+': lifecycle_does_not_change_selection')
            check(http('/publications/'+pub+'/api/objects')==objects and http('/publications/'+pub+'/offline.zip',binary=True)==package,label+': historical_online_and_offline_preserved')
            restored=change(space,candidate_key,'restore');check(restored['lifecycle_state']=='active' and restored['revision']==2,label+': candidate_restore_history_retained')
            # Unreferenced copy exercises input archival without replacing the current candidate.
            from packages.data.preview_inputs import PreviewInputs
            from packages.lifecycle.preview_spaces import PreviewSpaces
            directory=PreviewSpaces(output/'runtime/preview-directory');inputs=PreviewInputs(output/'runtime/preview-inputs',directory);original_input=inputs.read(input_id)
            spare=inputs.register('生命周期无引用样本',original_input['snapshot'],original_input.get('tracking'),space,original_input['format']);spare_key='input:'+spare['id']
            change(space,spare_key,'disable_input');change(space,spare_key,'archive_input');resume=change(space,spare_key,'restore')
            check(resume['lifecycle_state']=='disabled',label+': archived_disabled_input_resumes_disabled')
            change(space,spare_key,'restore');check(report(space,spare_key)['record']['revision']==4,label+': spare_input_history_complete')
            # Real subprocess admission after restoring source, keeping current selection/publication fixed.
            batch_now=http('/api/batches/'+sample['batch_id']+'?space_id='+space)['batch']
            job=http('/api/builds',{'space_id':space,'input_id':input_id,'batch_id':batch_now['id'],'batch_revision':batch_now['revision']},202)
            for _ in range(150):
                saved=next(j for j in http('/api/builds?space_id='+space)['jobs'] if j['id']==job['id'])
                if saved['state'] not in ('queued','running'):break
                time.sleep(.25)
            check(saved['state']=='succeeded',label+': restored_source_real_build_succeeded')
            check(http('/api/selection?space_id='+space)==selection,label+': rebuilt_candidate_not_selected')
            final=report(space,input_key);(output/(label+'-control.json')).write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            (output/(label+'-candidate-control.json')).write_text(json.dumps(report(space,candidate_key),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            samples.append({**sample,'spare_input_id':spare['id'],'new_build_id':job['id'],'control_revision':final['record']['revision']})
        check(inventory(Path('var/nyu'))==original,'original_managed_files_unchanged')
        check(inventory(source/'runtime')==source_before,'H1_source_runtime_unchanged')
        result={'profile':'cospace.preview-control-acceptance/0.1','passed':len(checks),'checks':checks,'samples':samples,'original_managed_files_unchanged':len(original),'H1_files_unchanged':len(source_before),'transport':'real_loopback_HTTP','publication_control_supported':False,'identity':'local_engineer_unverified_identity','quality':'unverified','robot_ready':False}
        (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        log.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())
if __name__=='__main__':main()
