import json
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_scene_ontology_links import publish_core


PREFLIGHT='/api/publication-semantic-preflight'


def seed(secured):
    rp,client,_,_,jobs,directory,spaces,_,old,new=secured
    headers,_=sign_in(secured,'usr_engineer')
    query=dict(space_id=spaces[0]['id'],candidate_id=new['candidate_id'])
    current=client.get('/api/scene-ontology-links',params=query).json()
    scope=json.dumps([rp.config.issuer,'org_mock','ws_mock'],separators=(',',':'))
    ref=publish_core(directory.root,scope)
    body=query|dict(source_sha256=current['source_sha256'],object_id=current['objects'][0]['object_id'],
        action='set',reference=ref,concept_id='physical_object',expected_revision=0,request_id='a'*32)
    assert client.post('/api/scene-ontology-links',json=body,headers=headers).status_code==200
    props={k:v for k,v in body.items() if k not in ('reference','concept_id')}
    props.update(action='properties',expected_revision=1,request_id='b'*32,
        properties={'name':{'value':'verified format, unverified field'}},valid_time=None,evidence_note='manual basis')
    assert client.post('/api/scene-ontology-links',json=props,headers=headers).status_code==200
    return query,dict(consumer_revision=2,source_manifest_sha256=current['source_sha256'])


def test_semantic_publication_explicit_preflight_authorization_frozen_files_and_replay(secured):
    _,client,_,_,jobs,directory,spaces,_,old,new=secured
    query,choice=seed(secured)
    headers,_=sign_in(secured,'usr_local_test')
    assert client.post(PREFLIGHT,json=query|{'semantic_selection':choice},headers=headers).status_code==403
    headers,_=sign_in(secured,'usr_manager')
    assert client.post(PREFLIGHT,json=query|{'semantic_selection':choice}).status_code==403
    response=client.post(PREFLIGHT,json=query|{'semantic_selection':choice},headers=headers)
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    selection=response.json()['semantic_selection']
    current=client.get('/api/selection',params={'space_id':query['space_id']}).json()
    request=query|dict(expected_revision=current['revision'],request_id='c'*32,semantic_selection=selection)
    response=client.post('/api/publications',json=request,headers=headers)
    assert response.status_code==201,response.text
    record=response.json()
    root=jobs.root/'publications'/record['id']
    assert 'semantic-artifact.json' in record['files']
    assert b'usr_engineer' not in (root/'claims.json').read_bytes()
    assert 'semantic_artifact' not in old
    assert client.post('/api/publications',json=request,headers=headers).json()['id']==record['id']
    wrong=request|{'semantic_selection':selection|{'consumer_revision':1}}
    assert client.post('/api/publications',json=wrong,headers=headers).status_code==409
    raw=(root/'claims.json').read_bytes()
    with __import__('sqlite3').connect(directory.root/'scene-ontology-links.sqlite3') as db:
        db.execute('DELETE FROM link_snapshots')
    assert client.post('/api/publications',json=request,headers=headers).json()['id']==record['id']
    assert (root/'claims.json').read_bytes()==raw
    assert client.get(record['preview_url']+'api/preview').status_code==200
    assert client.get(record['preview_url']+'offline.zip').status_code==200
    assert client.get(record['preview_url']+'partitions.zip').status_code==409
    manifest_record=root/'publication.json'
    saved=manifest_record.read_bytes()
    changed=json.loads(saved);del changed['semantic_artifact']
    manifest_record.write_text(json.dumps(changed))
    assert client.get(record['preview_url']+'api/preview').status_code==409
    manifest_record.write_bytes(saved)
    (root/'claims.json').write_bytes(b'corrupted')
    assert client.get(record['preview_url']+'api/preview').status_code==409


def test_preflight_denial_precedes_model_read_and_no_consumer_store_creation(secured,monkeypatch):
    _,client,_,_,jobs,directory,spaces,_,_,new=secured
    headers,_=sign_in(secured,'usr_other')
    def forbidden(*args,**kwargs):raise AssertionError('authorized first')
    monkeypatch.setattr(jobs,'model',forbidden)
    response=client.post(PREFLIGHT,json=dict(space_id=spaces[0]['id'],candidate_id=new['candidate_id'],
        semantic_selection={'consumer_revision':1,'source_manifest_sha256':'a'*64}),headers=headers)
    assert response.status_code==403
    assert not (directory.root/'scene-ontology-links.sqlite3').exists()


def test_failed_semantic_adoption_creates_no_visible_or_pending_publication(secured):
    _,client,_,_,jobs,_,_,_,_,_=secured
    query,choice=seed(secured)
    headers,_=sign_in(secured,'usr_manager')
    selected=client.get('/api/selection',params={'space_id':query['space_id']}).json()
    root=jobs.root/'publications'
    before={p.name for p in root.iterdir()}
    response=client.post('/api/publications',headers=headers,json=query|dict(
        expected_revision=selected['revision'],request_id='d'*32,
        semantic_selection=choice|{'snapshot_sha256':'f'*64}))
    assert response.status_code==409,response.text
    assert {p.name for p in root.iterdir()}==before
