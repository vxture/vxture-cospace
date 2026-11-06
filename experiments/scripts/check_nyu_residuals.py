"""Independently audit residual partitions and archive small evidence files."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('diagnostics',type=Path)
    p.add_argument('--original',type=Path,required=True); p.add_argument('--interior',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    r=json.loads((a.diagnostics/'diagnostics.json').read_bytes()); checks={}
    def check(name,value):
        checks[name]=bool(value)
        if not value: raise ValueError(name)
    for mode,path in [('original',a.original),('interior',a.interior)]:
        check(mode+'_report',sha(path/'comparison.json')==r[mode+'_sha256'])
    check('implementation',all(sha(Path(p))==digest for p,digest in r['implementation_sha256'].items()))
    check('entry_count',len(r['entries'])==28)
    for i,e in enumerate(r['entries']):
        full=e['full']; left=e['both_core']; right=e['other_matches']
        check(f'{i}_core_partition',left['count']+right['count']==full['count'] and
              np.isclose(left['squared_error_sum_m2']+right['squared_error_sum_m2'],full['squared_error_sum_m2']))
        for name in ['regions_4x3','target_depth_bands']:
            check(f'{i}_{name}',sum(b['count'] for b in e[name])==full['count'] and
                  np.isclose(sum(b['squared_error_sum_m2'] for b in e[name]),full['squared_error_sum_m2']))
        check(f'{i}_rmse',all(b['rmse_m'] is None if not b['count'] else
                  np.isclose(b['rmse_m']**2*b['count'],b['squared_error_sum_m2'])
                  for b in [full,left,right,*e['regions_4x3'],*e['target_depth_bands']]))
    check('research_only',not r['algorithm_ready'] and not r['real_release_ready'] and not r['independent_accuracy_verified'])
    a.output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(a.diagnostics/'diagnostics.json',a.output/'diagnostics.json')
    for mode,path in [('original',a.original),('interior',a.interior)]:
        shutil.copyfile(path/'comparison.json',a.output/f'{mode}.json')
    (a.output/'checks.json').write_text(json.dumps({'checks':checks,'checks_passed':len(checks),
        'files':{f.name:sha(f) for f in a.output.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'checks_passed':len(checks)}))


if __name__=='__main__': main()
