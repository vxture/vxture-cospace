"""Read-only independent consumer; secrets from caller-owned environment only."""
import argparse
import json
import os
from pathlib import Path
from pydantic import SecretStr
from packages.service.online_client import ClientConfig,OnlineClient


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--point',type=float,nargs=3,required=True)
    p.add_argument('--mode',choices=['historical','operational'],required=True);p.add_argument('--max-age-s',type=int,required=True)
    p.add_argument('--accept-unverified-time',action='store_true');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.exit(2,'exclusive_output_required\n')
    try:
        config=ClientConfig.model_validate_json(a.config.read_bytes())
        client=OnlineClient(config,os.environ.get('COSPACE_CONSUMER_CLIENT_ID'),SecretStr(os.environ.get('COSPACE_CONSUMER_CLIENT_SECRET','')))
        result=client.query(a.point,mode=a.mode,max_age_s=a.max_age_s,accept_unverified_time=a.accept_unverified_time)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps({'status':result['status'],'publication_id':result['publication_id'],'robot_ready':False}))
        if result['status']=='refused':raise SystemExit(3)
    except Exception:p.exit(2,'online_consumer_rejected; credentials and remote bodies omitted\n')


if __name__=='__main__':main()
