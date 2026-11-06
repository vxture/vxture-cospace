"""Download real publication, then compare a network-disabled child consumer."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('publication')
    parser.add_argument('--endpoint',default='http://127.0.0.1:8767')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    base=f'{args.endpoint}/publications/{args.publication}/'
    with urllib.request.urlopen(base+'offline.json') as response: info=json.load(response)
    with urllib.request.urlopen(base+'offline.zip') as response: data=response.read()
    bundle=args.output/'offline.zip'; bundle.write_bytes(data)
    with urllib.request.urlopen(base+'offline-checks.json') as response: points=json.load(response)
    child_code='''import json,socket,sys
from packages.views.agent.preview_offline import OfflinePreview
def denied(*args,**kwargs): raise RuntimeError("network disabled for offline verification")
socket.socket=denied
model=OfflinePreview.load(sys.argv[1],sys.argv[2],sys.argv[3])
print(json.dumps(model.query(json.loads(sys.argv[4]))))
'''
    results={}
    for name in ('surface','unknown'):
        point=points[name]['point_m']
        request=urllib.request.Request(base+'api/query',data=json.dumps({'point_m':point}).encode(),
                                       headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request) as response: online=json.load(response)
        child=subprocess.run([sys.executable,'-c',child_code,str(bundle.resolve()),
                              args.publication,info['sha256'],json.dumps(point)],
                             capture_output=True,text=True,check=True)
        offline=json.loads(child.stdout)
        assert online==offline
        assert offline['state']==('surface_candidate' if name=='surface' else 'unknown')
        results[name]={'online':online,'offline':offline,'equal':True}
    evidence={'package':info,'queries':results,'independent_process':True,
              'socket_creation_disabled_in_consumer':True,
              'physical_network_disconnection_tested':False}
    (args.output/'checks.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps({'bytes':len(data),'sha256':info['sha256'],'checks':'passed'}))


if __name__=='__main__': main()
