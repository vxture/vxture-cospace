"""Execute real CLI checks on generated bag bytes; refuse existing evidence roots."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

from experiments.scripts.bag_fixture import create_bag


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.output
    root.mkdir(parents=True,exist_ok=False)
    cases=[]
    for case,expected in [('valid',0),('missing_point_time',2),('backward_imu',2),('corrupt',2)]:
        bag=root/(case+'.bag')
        if case=='corrupt': bag.write_bytes(b'synthetic corrupt input')
        else: create_bag(bag,case)
        command=[sys.executable,'-m','experiments.scripts.inspect_bag_offline',str(bag),
                 '--expected-sha256',hashlib.sha256(bag.read_bytes()).hexdigest(),
                 '--output',str(root/(case+'.json'))]
        process=subprocess.run(command,capture_output=True,text=True,timeout=30)
        cases.append({'case':case,'expected_exit':expected,'actual_exit':process.returncode,
                      'command':command,'stdout':process.stdout,'stderr':process.stderr,
                      'input_bytes':bag.stat().st_size,'input_sha256':hashlib.sha256(bag.read_bytes()).hexdigest()})
    files=['packages/data/bag_preflight.py','experiments/scripts/inspect_bag_offline.py',
           'experiments/scripts/bag_fixture.py','experiments/scripts/smoke_bag_offline.py','uv.lock']
    metadata=importlib.metadata.distribution('rosbags')
    for name in ('METADATA','LICENSE.txt'):
        member=next(p for p in metadata.files if p.name==name and '.dist-info' in str(p))
        (root/('rosbags-'+name)).write_bytes(Path(metadata.locate_file(member)).read_bytes())
    report={'data_kind':'synthetic_test_fixture_not_truth','passed':all(c['actual_exit']==c['expected_exit'] for c in cases),
            'python':sys.version,'platform':platform.platform(),
            'dependencies':{n:importlib.metadata.version(n) for n in ('rosbags','numpy','apsw','lz4','ruamel.yaml')},
            'implementation_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},
            'cases':cases,'slam_executed':False,'algorithm_ready':False,'real_data_validated':False}
    (root/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'cases':len(cases),'slam_executed':False}))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
