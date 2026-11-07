import json
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest
from fastapi.testclient import TestClient
from packages.lifecycle.preview_control import ControlChange
from packages.data.preview_artifacts import artifact_catalog
from packages.service.preview_workflow import workflow
from packages.views.agent.preview_offline import OfflinePreview,export_bundle,sha
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_control import payload,run
from test_preview_impact import seed

def endpoints(pub,model):
    prefix='/publications/'+pub['id']
    bounds=[[min(c[i] for c in model.cells)*model.resolution-model.resolution for i in range(3)],[(max(c[i] for c in model.cells)+2)*model.resolution for i in range(3)]]
    point=tuple((c+.5)*model.resolution for c in next(iter(model.cells)))
    return [('GET',prefix+'/api/preview',None),('GET',prefix+'/api/objects',None),('GET',prefix+'/api/objects/room-a',None),
            ('GET',prefix+'/api/checklist',None),('GET',prefix+'/api/lineage',None),
            ('POST',prefix+'/api/query',{'point_m':list(point)}),
            ('POST',prefix+'/api/query-range',{'bounds_m':bounds,'frame_id':model.manifest['frame_id'],'limit':4096}),
            ('GET',prefix+'/',None),('GET',prefix+'/offline.zip',None),('GET',prefix+'/offline.json',None),
            ('GET',prefix+'/partitions.zip',None),('GET',prefix+'/partitions.json',None),
            *[('GET',prefix+'/'+name,None) for name in (*pub['files'],'publication.json')]]

def test_pause_all_distribution_paths_and_restore_exact_bytes(tmp_path):
    initial,jobs,directory,spaces,ontologies,pubs,old,new,_=seed(tmp_path);space=spaces[0]['id'];key='publication:'+new['id'];store=jobs.controls
    record,model=pubs.read(new['id']);paths=endpoints(record,model);files={p.name:p.read_bytes() for p in model.root.iterdir() if p.is_file()}
    report=store.report(pubs,space,key);assert report['publication_control_supported'] and report['record']['revision']==0
    assert report['actions'][0]['operation']=='pause_distribution'
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        before={(method,path):client.request(method,path,json=body).content for method,path,body in paths}
        assert all(client.request(method,path,json=body).status_code==200 for method,path,body in paths)
        zip_before=before['GET','/publications/'+new['id']+'/offline.zip'];offline=OfflinePreview(zip_before,new['id'],sha(zip_before));objects=offline.objects()
        paused=run(store,pubs,space,key,'pause_distribution');assert paused['lifecycle_state']=='paused' and paused['resume_state'] is None
        for method,path,body in paths:
            response=client.request(method,path,json=body)
            assert response.status_code==409,(path,response.text)
            assert response.json()['detail']=='publication_distribution_paused' and response.headers['Cache-Control']=='no-store'
        assert client.get('/publications/'+old['id']+'/api/objects').status_code==200
        assert offline.objects()==objects # An already held package is not remotely invalidated.
        restored=run(store,pubs,space,key,'restore');assert restored['lifecycle_state']=='active' and restored['revision']==2
        for method,path,body in paths:
            response=client.request(method,path,json=body);assert response.status_code==200
            # Checklist/lineage carry checked_at, unlike immutable assets and query records.
            if not path.endswith(('api/checklist','api/lineage')):assert response.content==before[method,path],path
            assert response.headers['Cache-Control']=='no-store'
    assert {p.name:p.read_bytes() for p in model.root.iterdir() if p.is_file()}==files

def test_conditional_range_head_redirect_and_encoded_paths_cannot_bypass(tmp_path):
    initial,jobs,directory,spaces,ontologies,pubs,_,new,_=seed(tmp_path);space=spaces[0]['id'];base='/publications/'+new['id']
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        asset=client.get(base+'/model.json');etag=asset.headers['etag'];assert asset.headers['Cache-Control']=='no-store'
        run(jobs.controls,pubs,space,'publication:'+new['id'],'pause_distribution')
        for method,path,headers in [('GET',base+'/model.json',{'If-None-Match':etag}),('GET',base+'/agent.npz',{'Range':'bytes=0-10'}),('HEAD',base+'/offline.zip',{}),('GET',base,{}),('GET',base+'/unknown/path',{}),('GET','/publications/'+new['id']+'%2Fmodel.json',{}),('GET','/publications%5C'+new['id']+'%5Cmodel.json',{})]:
            assert client.request(method,path,headers=headers,follow_redirects=False).status_code==409,(method,path)

def test_management_metadata_and_no_default_fallback_or_comparison_bypass(tmp_path):
    initial,jobs,directory,spaces,ontologies,pubs,old,new,_=seed(tmp_path);space=spaces[0]['id'];key='publication:'+new['id']
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        run(jobs.controls,pubs,space,key,'pause_distribution')
        listing=client.get('/api/publications',params={'space_id':space}).json()['publications'];paused=next(p for p in listing if p['id']==new['id'])
        assert paused['lifecycle_state']=='paused' and 'files' not in paused and 'selection_review' not in paused and 'preview_url' not in paused
        entry=next(s for s in client.get('/api/spaces').json()['spaces'] if s['id']==space)
        assert entry['publication_id'] is None and entry['state']=='distribution_paused'
        assert client.get('/api/spaces/'+space).json()['publication_id'] is None
        assert any(p['id']==old['id'] and p['lifecycle_state']=='active' for p in entry['publications'])
        for base,target in ((old['id'],new['id']),(new['id'],old['id'])):
            response=client.post('/api/publication-comparisons',json={'space_id':space,'base_publication_id':base,'target_publication_id':target});assert response.status_code==409
        items=artifact_catalog(pubs,space)['items']
        for item in items:
            if item['record_id']==new['id']:assert item['lifecycle_state']=='paused' and item['resources']=={}
        state=workflow(pubs,space);stages={s['id']:s for s in state['stages']}
        assert state['publication_ref']['publication_id']==new['id'] and stages['delivery']['status']==stages['space']['status']=='blocked'
        assert stages['space']['action']['module']=='delivery'
        assert client.get('/api/artifact-control',params={'space_id':space,'artifact':key}).status_code==200

def test_history_scope_revision_and_restart_remain_controlled(tmp_path):
    initial,jobs,directory,spaces,ontologies,pubs,_,new,_=seed(tmp_path);space=spaces[0]['id'];key='publication:'+new['id'];store=jobs.controls
    request=payload(store,pubs,space,key,'pause_distribution');store.change(pubs,request)
    with pytest.raises(ValueError,match='changed_refresh'):store.change(pubs,request)
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        assert client.get('/publications/'+new['id']+'/api/preview').status_code==409
        assert client.get('/api/artifact-control',params={'space_id':spaces[1]['id'],'artifact':key}).status_code==404
        assert client.post('/api/artifact-control/transitions',json=payload(store,pubs,space,key,'restore').model_dump(),headers={'Origin':'https://example.com'}).status_code==403
        assert client.post('/api/artifact-control/transitions',json=request.model_dump()|{'operation':'delete'}).status_code==422
    from packages.lifecycle.preview_control import PreviewControls
    reopened=PreviewControls(store.runtime,directory);saved=reopened.read(space,key);assert saved['lifecycle_state']=='paused' and len(saved['history'])==1
    assert run(reopened,pubs,space,key,'restore')['revision']==2
    from jsonschema import Draft202012Validator,FormatChecker
    Draft202012Validator(json.loads(Path('contracts/schemas/preview-artifact-control-v0.1.schema.json').read_bytes()),format_checker=FormatChecker()).validate(reopened.report(pubs,space,key))

@pytest.mark.parametrize('damage',['database','events','ownership','manifest'])
def test_corrupted_distribution_records_fail_closed_without_assets(tmp_path,damage):
    initial,jobs,directory,spaces,ontologies,pubs,_,new,_=seed(tmp_path);space=spaces[0]['id'];key='publication:'+new['id']
    run(jobs.controls,pubs,space,key,'pause_distribution')
    if damage=='database':jobs.controls.path.write_bytes(b'damaged')
    elif damage=='events':
        with sqlite3.connect(jobs.controls.path) as db:db.execute('DELETE FROM events WHERE artifact=?',(key,))
    elif damage=='ownership':
        path=pubs.root/new['id']/'publication.json';data=json.loads(path.read_bytes());data.pop('space_id');data.pop('project_id');path.write_text(json.dumps(data))
    else:(pubs.root/new['id']/'model.json').write_bytes(b'broken')
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client:
        for path in ('api/preview','human.ply','offline.zip'):
            response=client.get('/publications/'+new['id']+'/'+path);assert response.status_code==409 and 'detail' in response.json()

def test_pause_restore_requires_complete_saved_evidence_and_transaction_rollback(tmp_path):
    _,jobs,_,spaces,_,pubs,_,new,_=seed(tmp_path);space=spaces[0]['id'];key='publication:'+new['id'];store=jobs.controls
    run(store,pubs,space,key,'pause_distribution');request=payload(store,pubs,space,key,'restore')
    with sqlite3.connect(store.path) as db:db.execute("CREATE TRIGGER reject_update BEFORE UPDATE ON controls BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError):store.change(pubs,request)
    assert store.read(space,key)['lifecycle_state']=='paused' and len(store.read(space,key)['history'])==1
    (pubs.root/new['id']/'agent.npz').write_bytes(b'broken')
    report=store.report(pubs,space,key);assert not report['actions'][0]['allowed']

def test_two_pause_requests_only_one_commits(tmp_path):
    _,jobs,_,spaces,_,pubs,_,new,_=seed(tmp_path);space=spaces[0]['id'];key='publication:'+new['id'];store=jobs.controls;request=payload(store,pubs,space,key,'pause_distribution')
    def writer():
        try:return store.change(pubs,request)['revision']
        except ValueError:return 'conflict'
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:writer(),range(2)))
    assert results.count(1)==1 and store.read(space,key)['revision']==1

def test_static_alias_to_publication_is_rejected(tmp_path):
    _,jobs,directory,_,ontologies,pubs,_,new,_=seed(tmp_path)
    with pytest.raises(ValueError,match='static_alias'):create_app(pubs.root/new['id'],jobs,space_directory=directory,ontologies=ontologies)
    with pytest.raises(ValueError,match='static_alias'):create_app(pubs.root/new['id'])

def test_request_admitted_before_pause_can_finish_but_next_request_is_denied(tmp_path,monkeypatch):
    initial,jobs,directory,spaces,ontologies,pubs,_,new,_=seed(tmp_path);space=spaces[0]['id'];key='publication:'+new['id']
    from packages.service.preview_publications import PreviewPublications
    entered=threading.Event();release=threading.Event();original=PreviewPublications.require_distributing
    def held(self,identity):
        result=original(self,identity)
        if identity==new['id'] and not entered.is_set():entered.set();assert release.wait(5)
        return result
    monkeypatch.setattr(PreviewPublications,'require_distributing',held)
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies)) as client,ThreadPoolExecutor(1) as pool:
        pending=pool.submit(client.get,'/publications/'+new['id']+'/api/preview');assert entered.wait(5)
        run(jobs.controls,pubs,space,key,'pause_distribution');release.set();assert pending.result().status_code==200
        assert client.get('/publications/'+new['id']+'/api/preview').status_code==409
