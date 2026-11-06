"""Acquire one fixed official NCLT sensor archive and copy only its ms25 CSV."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

URL='https://s3.us-east-2.amazonaws.com/nclt.perl.engin.umich.edu/sensor_data/2013-01-10_sen.tar.gz'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.output
    root.mkdir(parents=True,exist_ok=False)
    record={'dataset':'NCLT','sequence':'2013-01-10','url':URL,
            'source_page':'https://robots.engin.umich.edu/nclt/',
            'license':'ODbL-1.0 + DbCL-1.0; attribution and redistribution obligations apply',
            'role':'development_input','data_kind':'public_recorded',
            'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'completed':False,'algorithm_ready':False,'real_release_ready':False}
    try:
        archive=root/'sensor.tar.gz'
        sha=hashlib.sha256(); size=0
        with urllib.request.urlopen(URL,timeout=30) as response, archive.open('xb') as target:
            record.update(http_status=response.status,final_url=response.url,etag=response.headers.get('ETag'))
            while block:=response.read(1024*1024):
                size+=len(block)
                if size>32*1024*1024: raise ValueError('archive_download_budget')
                target.write(block); sha.update(block)
        record['archive']={'path':str(archive),'bytes':size,'sha256':sha.hexdigest()}
        print(json.dumps({'downloaded_bytes':size}),flush=True)
        members=[]; selected=[]; total=0
        with tarfile.open(archive,'r:gz') as bundle:
            for member in bundle:
                total+=member.size
                if len(members)>=128 or total>512*1024*1024: raise ValueError('archive_member_budget')
                members.append({'name':member.name,'bytes':member.size,'regular':member.isfile()})
                if member.name.split('/')[-1]=='ms25.csv':
                    if not member.isfile() or member.size>64*1024*1024: raise ValueError('csv_member_budget')
                    stream=bundle.extractfile(member)
                    raw=stream.read(64*1024*1024+1)
                    if len(raw)!=member.size: raise ValueError('csv_truncated')
                    selected.append((member.name,raw))
        if len(selected)!=1: raise ValueError('expected_exactly_one_ms25')
        name,raw=selected[0]
        # Fixed output basename; no extractall or use of archive paths for destination writes.
        (root/'ms25.csv').write_bytes(raw)
        record.update(completed=True,members=members,
                      selected={'archive_member':name,'path':str(root/'ms25.csv'),
                                'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    except Exception as error:
        record['error']=str(error)
        raise
    finally:
        (root/'acquisition.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'completed':True,'selected':record['selected']}))


if __name__=='__main__': main()
