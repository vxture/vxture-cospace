"""Fetch bounded public dataset documentation for a new source-review directory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

SOURCES = {
    'openloris-home':'https://lifelong-robotic-vision.github.io/dataset/scene.html',
    'vbr-home':'https://rvp-group.net/slam-dataset.html',
    'vbr-repository':'https://raw.githubusercontent.com/rvp-group/vbr-devkit/main/README.md',
    'botanic-home':'https://botanicgarden.ipb.uni-bonn.de/',
    'nclt-home':'https://robots.engin.umich.edu/nclt/',
}
DETAILS = {
    'vbr-dataset-script':'https://rvp-group.net/js/slam-dataset.js',
    'nclt-ms25-reader':'https://s3.us-east-2.amazonaws.com/nclt.perl.engin.umich.edu/python/read_ms25.py',
    'nclt-imu-converter':'https://s3.us-east-2.amazonaws.com/nclt.perl.engin.umich.edu/python/ms25_to_rosbag.py',
    'nclt-vel-reader':'https://s3.us-east-2.amazonaws.com/nclt.perl.engin.umich.edu/python/read_vel_hits.py',
    'odbl-license':'https://opendatacommons.org/licenses/odbl/1-0/',
    'dbcl-license':'https://opendatacommons.org/licenses/dbcl/1-0/',
}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stage',choices=('initial','details'),default='initial')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    def fetch(item):
        name,url=item
        record={'name':name,'url':url,'fetched_at_utc':datetime.now(timezone.utc).isoformat()}
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'CoSpace-input-source-review/0.1'})
            with urllib.request.urlopen(request,timeout=25) as response:
                raw=response.read(2*1024*1024+1)
                if len(raw)>2*1024*1024: raise ValueError('documentation_limit')
                record.update(status=response.status,final_url=response.url,
                              content_type=response.headers.get('Content-Type'),
                              sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),file=name+'.txt')
                (args.output/(name+'.txt')).write_bytes(raw)
        except (OSError,ValueError) as error:
            record.update(status=getattr(error,'code',None),error=str(error))
        return record
    with ThreadPoolExecutor(max_workers=5) as pool:
        records=list(pool.map(fetch,(SOURCES if args.stage=='initial' else DETAILS).items()))
    (args.output/'sources.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{k:r.get(k) for k in ('name','status','error')} for r in records]))


if __name__=='__main__':
    main()
