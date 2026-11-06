"""Read-only inventory and bounded header sampling of user-provided NYU raw offices."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    scenes=[]
    for directory in sorted(args.root.iterdir()):
        if not directory.is_dir(): continue
        counts=Counter(); size=0; samples={}
        for path in directory.iterdir():
            if not path.is_file(): continue
            counts[path.suffix.lower()]+=1; size+=path.stat().st_size
            if path.suffix in ('.ppm','.pgm','.dump') and path.suffix not in samples:
                with path.open('rb') as source: header=source.read(80)
                samples[path.suffix]={'name':path.name,'bytes':path.stat().st_size,'first_80_bytes_hex':header.hex(),
                                      'header_repr':repr(header)}
        scenes.append({'scene':directory.name,'counts':dict(counts),'bytes':size,'samples':samples})
    result={'root':str(args.root),'scenes':scenes,'scene_count':len(scenes),
            'counts':dict(sum((Counter(s['counts']) for s in scenes),Counter())),
            'total_bytes':sum(s['bytes'] for s in scenes),'payloads_fully_validated':False}
    (args.output/'inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    url='https://cs.nyu.edu/~fergus/datasets/nyu_depth_v2.html'
    with urllib.request.urlopen(url,timeout=25) as response: raw=response.read(1024*1024)
    (args.output/'nyu-official-page.html').write_bytes(raw)
    (args.output/'source.json').write_text(json.dumps({'url':url,'read_at_utc':datetime.now(timezone.utc).isoformat(),
        'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)},indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('scene_count','counts','total_bytes')}))
    print(json.dumps(scenes[0],ensure_ascii=False))


if __name__=='__main__': main()
