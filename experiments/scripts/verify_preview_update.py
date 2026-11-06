"""Exercise a new candidate, fixed publication and explicit local consumer update."""
import argparse
import json
from pathlib import Path
import socket
import time
import urllib.request
from packages.views.agent.preview_consumer import PreviewConsumer
from packages.views.agent.preview_offline import sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',default='http://127.0.0.1:8767')
    parser.add_argument('--previous',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)

    def request(path, body=None):
        req=urllib.request.Request(args.endpoint+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response: return response.read()

    def api(path,body=None): return json.loads(request(path,body))

    def download(identity):
        base=f'/publications/{identity}/'
        info=api(base+'offline.json'); data=request(base+'offline.zip')
        assert sha(data)==info['sha256']
        path=args.output/(identity+'.zip'); path.write_bytes(data)
        return path,identity,info['sha256']

    old=download(args.previous)
    old_manifest=api(f'/publications/{args.previous}/publication.json')
    point=api(f'/publications/{args.previous}/offline-checks.json')['surface']['point_m']
    consumer=PreviewConsumer(); first=consumer.activate(*old,expected_revision=0)
    before=first.query(point)
    selection=api('/api/selection')
    inputs=api('/api/inputs')
    job=api('/api/builds',{'input_id':inputs['inputs'][0]['id']} if inputs['selection_required'] else {})
    deadline=time.monotonic()+130
    while time.monotonic()<deadline:
        current=next(j for j in api('/api/builds')['jobs'] if j['id']==job['id'])
        if current['state'] not in ('queued','running'): break
        time.sleep(1)
    else: raise RuntimeError('build_verification_timeout')
    if current['state']!='succeeded': raise RuntimeError(str(current))
    selected=api('/api/selection',{'candidate_id':job['id'],'expected_revision':selection['revision']})
    record=api('/api/publications',{'candidate_id':job['id'],'expected_revision':selected['revision']})
    new=download(record['id'])
    assert consumer.session() is first and consumer.status()['revision']==1
    online=api(record['query_url'],{'point_m':point})
    assert api(f'/publications/{args.previous}/publication.json')==old_manifest
    # Finish all HTTP operations before blocking sockets in the consumer process.
    original_socket=socket.socket
    def denied(*args,**kwargs): raise RuntimeError('consumer network disabled')
    socket.socket=denied
    try:
        second=consumer.activate(*new,expected_revision=1)
        after=second.query(point)
        assert {k:v for k,v in after.items() if k not in ('consumer_revision','package_sha256')}==online
        assert first.query(point)==before
        stale_refused=False
        try: consumer.activate(*old,expected_revision=1)
        except ValueError as exc: stale_refused=str(exc)=='consumer_revision_changed'
        assert stale_refused and consumer.session() is second
        review=consumer.activate(*old,expected_revision=2).query(point)
        assert review['publication_id']==args.previous and review['consumer_revision']==3
        assert second.query(point)==after
    finally: socket.socket=original_socket
    evidence={'previous_publication':old_manifest,'new_publication':record,
        'build':current,'download_only_did_not_activate':True,
        'old_session_unchanged':True,'old_publication_unchanged':True,
        'stale_activation_refused':stale_refused,'socket_creation_disabled_during_switch':True,
        'before':before,'after':after,'historical_review':review,'online_new':online,
        'geometry_changed':old_manifest['source_model_sha256']!=record['source_model_sha256'],
        'scope':'same frozen input rebuilt; version workflow only, not incremental reconstruction'}
    (args.output/'checks.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps({'checks':'passed','new_publication':record['id'],
                      'new_candidate':job['id'],'geometry_changed':evidence['geometry_changed']}))


if __name__=='__main__': main()
