"""Read-only local inventory and format sanity checks; no algorithm evaluation."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import struct


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('new output required')
    files=[p for p in args.root.rglob('*') if p.is_file() and '.git' not in p.relative_to(args.root).parts]
    counts=Counter(p.suffix.lower() or '(none)' for p in files)
    result={'root':str(args.root),'file_count':len(files),'extensions':dict(sorted(counts.items())),
            'recordings':[p.relative_to(args.root).as_posix() for p in files if p.suffix.lower() in ('.db3','.bag','.mcap') or p.name=='metadata.yaml'],
            'floorplans':[],'trajectories':[],'source_hashes':{},'algorithm_executed':False}
    for p in files:
        rel=p.relative_to(args.root).as_posix()
        if rel.startswith(('docs/','config/')) or rel in ('README.md','LICENSE','challenge_tools_ros/runtime_helper/map_server.py'):
            result['source_hashes'][rel]=hashlib.sha256(p.read_bytes()).hexdigest()
        if rel.startswith('floorplans/'):
            raw=p.read_bytes()
            record={'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            if raw.startswith(b'\x89PNG\r\n\x1a\n'):
                width,height=struct.unpack('>II',raw[16:24])
                record.update(width=width,height=height,bit_depth=raw[24],color_type=raw[25])
            else: record['png_header_valid']=False
            result['floorplans'].append(record)
        if rel.startswith('groundtruth/') and p.suffix=='.txt':
            raw=p.read_bytes(); previous=None; times=[]; invalid=0; backward=0; duplicate=0; deviation=0.0
            for line in raw.decode().splitlines():
                if not line.strip() or line.lstrip().startswith('#'): continue
                parts=line.split()
                if len(parts)!=8: invalid+=1; continue
                try:
                    at=Decimal(parts[0]); values=list(map(float,parts[1:]))
                    if not at.is_finite() or not all(map(math.isfinite,values)): raise ValueError('nonfinite')
                except (ValueError,ArithmeticError): invalid+=1; continue
                if previous is not None: backward+=int(at<previous); duplicate+=int(at==previous)
                previous=at; times.append(at)
                deviation=max(deviation,abs(math.sqrt(sum(v*v for v in values[3:]))-1))
            result['trajectories'].append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                 'rows':len(times),'invalid_rows':invalid,'backward_steps':backward,'duplicate_steps':duplicate,
                 'start_seconds':str(min(times)) if times else None,'end_seconds':str(max(times)) if times else None,
                 'max_quaternion_norm_deviation':deviation})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'files':len(files),'recordings':result['recordings'],
                      'floorplans':len(result['floorplans']),'trajectories':len(result['trajectories']),
                      'trajectory_rows':sum(t['rows'] for t in result['trajectories']),
                      'invalid_rows':sum(t['invalid_rows'] for t in result['trajectories']),
                      'backward_steps':sum(t['backward_steps'] for t in result['trajectories']),
                      'duplicate_steps':sum(t['duplicate_steps'] for t in result['trajectories'])}))


if __name__=='__main__': main()
