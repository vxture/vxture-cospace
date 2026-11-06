"""P8: verify the actual browser-downloaded bundle in independent offline consumers."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from packages.views.agent.preview_offline import sha


def cli_result(path):
    value=path.read_text(encoding='utf-8-sig')
    match=re.search(r'### Result\s*\n(.*?)\n### Ran',value,re.S)
    if not match:raise ValueError('browser_result_missing')
    result=json.loads(match[1])
    if result['status']!='passed':raise ValueError('browser_acceptance_required')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--browser-main',type=Path,required=True)
    p.add_argument('--browser-extra',type=Path,required=True)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--query-plan',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    main=cli_result(a.browser_main);extra=cli_result(a.browser_extra)
    plan=json.loads(a.query_plan.read_bytes());raw=a.bundle.read_bytes()
    assert main['publication_id']==extra['publication_id']==plan['publication']
    assert main['space_id']==extra['space_id']==plan['space']
    assert sha(raw)==main['package_sha256']==plan['sha256']
    bundle=a.output/'consumer-source.zip';shutil.copyfile(a.bundle,bundle)
    release={'id':plan['publication'],'sha256':plan['sha256'],'bundle':str(bundle.resolve()),
             'point':plan['point'],'unknown':plan['unknown'],'bounds':plan['bounds'],
             'frame_id':plan['frame_id'],'online':extra['online']}
    if 'expected_source' in plan:release['expected_source']=plan['expected_source']
    if 'expected_objects' in plan:release['expected_objects']=plan['expected_objects']
    results=[]
    for mode in ('install_first','activate_first','restore_first'):
        if mode=='restore_first':bundle.rename(a.output/'export-evidence.zip')
        target=a.output/(mode+'-result.json')
        request={'root':str((a.output/'consumer').resolve()),'mode':mode,'releases':[release,release],
                 'space':plan['space'],'result':str(target.resolve())}
        request_path=a.output/(mode+'-request.json')
        request_path.write_text(json.dumps(request,indent=2)+'\n',encoding='utf-8')
        subprocess.run([sys.executable,'-X','utf8','-m','experiments.scripts.verify_release_consumption',
                        '--consumer-request',str(request_path)],check=True,timeout=40)
        value=json.loads(target.read_bytes());assert value['network_disabled']
        if mode!='install_first':assert value['results']==extra['online']
        results.append(value)
    assert len({r['pid'] for r in results})==3
    assert extra['online']['point']['state']=='surface_candidate'
    assert extra['online']['unknown']['state']=='unknown'
    assert extra['online']['range']['returned_cells']==1
    checks=['browser_download_digest_matches_fixed_package','three_distinct_network_disabled_processes',
            'install_does_not_activate','explicit_activation_matches_online_point_unknown_and_range',
            'restart_requires_explicit_restore','restore_succeeds_without_original_export_file',
            'restored_queries_match_same_online_publication']
    report={'status':'passed','passed':len(checks),'checks':checks,'space_id':plan['space'],
            'publication_id':plan['publication'],'sha256':plan['sha256'],
            'processes':[{'mode':r['mode'],'pid':r['pid'],'checks':r['checks']} for r in results],
            'quality':'unverified','production_ready':False,'robot_ready':False}
    (a.output/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
