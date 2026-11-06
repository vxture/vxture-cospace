"""P10 uploaded sample provenance and independently restarted offline consumers.

Reads actual browser downloads and online query receipts. Does not contact the
server, rebuild, select candidates, or publish during verification.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from experiments.scripts.verify_scene_journey_consumer import cli_result
from packages.views.agent.preview_offline import OfflinePreview,sha


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verify(args):
    main=cli_result(args.browser_main);extra=cli_result(args.browser_extra)
    output=args.output.resolve();original=Path('var/nyu').resolve()
    if output.is_relative_to(original) or original.is_relative_to(output):raise ValueError('exclusive_output_outside_original_required')
    output.mkdir(parents=True,exist_ok=False);checks=[];results=[];pids=set()
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    for index,item in enumerate(main['results']):
        observed=next(v for v in extra['results'] if v['publication_id']==item['publication_id'])
        check(observed['space_id']==item['space_id'],f'sample_{index}_online_receipt_has_same_scene')
        raw=Path(item['bundle']).read_bytes();check(sha(raw)==item['package_sha256'],f'sample_{index}_browser_download_digest_matches')
        offline=OfflinePreview(raw,item['publication_id'],item['package_sha256']);source=offline.manifest['source']
        check(source['input_binding']['id']==item['input_id'] and
              source['input_binding']['registration_ref']['package_sha256']==item['upload_sha256'],f'sample_{index}_package_keeps_original_upload_receipt')
        check(source['batch_ref']['batch_id']==item['batch_id'] and source['batch_ref']['admitted_revision']==item['batch_revision'],f'sample_{index}_package_keeps_sealed_batch_revision')
        root=output/f'sample-{index}';root.mkdir();bundle=root/'consumer-source.zip';shutil.copyfile(item['bundle'],bundle)
        release={'id':item['publication_id'],'sha256':item['package_sha256'],'bundle':str(bundle),
            'point':observed['point'],'unknown':observed['unknown'],'bounds':observed['bounds'],
            'frame_id':observed['frame_id'],'online':observed['online'],'expected_source':source}
        process_results=[]
        for mode in ('install_first','activate_first','restore_first'):
            if mode=='restore_first':bundle.rename(root/'export-evidence.zip')
            target=root/(mode+'-result.json');request=root/(mode+'-request.json')
            save(request,{'root':str(root/'consumer'),'mode':mode,'releases':[release,release],
                          'space':item['space_id'],'result':str(target)})
            subprocess.run([sys.executable,'-X','utf8','-m','experiments.scripts.verify_release_consumption',
                            '--consumer-request',str(request)],check=True,timeout=40)
            value=json.loads(target.read_bytes());check(value['network_disabled'],f'sample_{index}_{mode}_network_disabled')
            if mode!='install_first':check(value['results']==observed['online'],f'sample_{index}_{mode}_queries_equal_online')
            pids.add(value['pid']);process_results.append({'mode':mode,'pid':value['pid'],'checks':value['checks']})
        check(observed['online']['point']['state']=='surface_candidate' and observed['online']['unknown']['state']=='unknown'
              and observed['online']['range']['returned_cells']==1,f'sample_{index}_surface_unknown_and_range_are_consistent')
        results.append(item|{'offline_bytes':len(raw),'source':source,'processes':process_results})
    check(len(pids)==len(main['results'])*3,'each_install_activation_and_restore_uses_a_distinct_process')
    # Both inputs belong to different physical scenes. An offline store must not
    # install the other scene's package even though both came from this platform.
    from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
    foreign=PersistentPreviewConsumer.initialize(output/'cross-scene-consumer',main['results'][0]['space_id'])
    second=main['results'][1]
    try:foreign.install(second['bundle'],second['publication_id'],second['package_sha256'])
    except ValueError as exc:check(str(exc)=='consumer_space_mismatch','foreign_scene_offline_install_is_rejected')
    else:raise AssertionError('cross_scene_install_was_accepted')
    report={'status':'passed','passed':len(checks),'checks':checks,'results':results,'offline_processes':len(pids),
            'identity_provider':'local_mock_only','quality':'unverified','production_ready':False,'robot_ready':False}
    save(output/'acceptance.json',report)
    print(json.dumps({'status':'passed','passed':len(checks),'offline_processes':len(pids),'samples':len(results)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--browser-main',type=Path,required=True)
    parser.add_argument('--browser-extra',type=Path,required=True);verify(parser.parse_args())
