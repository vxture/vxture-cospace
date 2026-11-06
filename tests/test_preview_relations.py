from copy import deepcopy
import io
import json
from pathlib import Path
import zipfile
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from test_preview_objects import fixture
from packages.ontology.preview_versions import definition
from packages.ontology.preview_relations import inspect_relations
from packages.spatial.preview_objects import SemanticRequest
from packages.spatial.preview_relations import RelationRequest
from packages.construction.preview_semantics import annotate,ObjectRulesFailed
from packages.construction.preview_relations import relate
from packages.construction.preview_model import PreviewModel,digest
from packages.construction.preview_changes import CompareRequest,ReviewRequest,compare,confirm
from packages.service.preview_publications import PreviewPublications
from packages.service.preview_publication_changes import PublicationCompareRequest,compare_publications
from packages.views.agent.preview_offline import OfflinePreview,export_bundle,sha
from experiments.scripts.serve_nyu_flow_preview import create_app

SEED=Path('configs/ontology/indoor-equipment-v0.2.json')
def relation(identity='contains-1',kind='contains',source='room-a',target='cabinet-a'):
    return {'relation_id':identity,'type_id':kind,'source_id':source,'target_id':target,'note':'流程测试人工声明，非现场确认'}

def setup(tmp_path):
    initial,jobs,directory,spaces,store,body=fixture(tmp_path)
    body['objects']=[{'object_id':i,'type_id':t,'properties':{'name':i+' 待核实'},'point_index':0}
        for i,t in [('room-a','room'),('corridor-a','corridor'),('room-b','room'),('cabinet-a','cabinet')]]
    # Keep a legacy semantic base/publication to verify explicit rule upgrade.
    legacy=annotate(jobs,store,SemanticRequest(**body));selection=jobs.select(legacy['id'],0,spaces[0]['id'])
    pubs=PreviewPublications(jobs);old=pubs.publish(legacy['id'],selection['revision'],spaces[0]['id'])
    record=store.register(SEED);base=jobs.model(legacy['id'])
    request={'space_id':spaces[0]['id'],'base_candidate_id':legacy['id'],'base_manifest_sha256':digest(base.root/'model.json'),
             'ontology_ref':{k:record[k] for k in ('ontology_id','version','sha256')},
             'relations':[relation(),relation('connect-1','connected_to','room-a','corridor-a')]}
    return initial,jobs,directory,spaces,store,pubs,old,request

def files(root):return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

def test_rule_versions_and_invalid_definitions(tmp_path):
    _,_,_,_,store,_,_,_=setup(tmp_path)
    old=store.read('indoor-equipment','0.1.0')[1];new=store.read('indoor-equipment','0.2.0')[1]
    assert 'relations' not in old and old['types']==new['types']
    assert store.list()[-1]['relation_count']==3
    for change in ['unknown_type','symmetric_types','symmetric_containment','no_parent','duplicate_endpoint_type']:
        doc=deepcopy(new)
        if change=='unknown_type':doc['relations']['contains']['source_types']=['unknown']
        elif change=='symmetric_types':doc['relations']['connected_to']['source_types']=['room']
        elif change=='symmetric_containment':doc['relations']['contains']['symmetric']=True
        elif change=='no_parent':del doc['relations']['contains']['parent_endpoint']
        else:doc['relations']['contains']['source_types']=['room','room']
        with pytest.raises(ValueError):definition(json.dumps(doc).encode())
    for raw in (b'[]',b'null',b'1'):
        with pytest.raises(ValueError):definition(raw)

def test_relation_candidate_review_publication_and_offline(tmp_path):
    initial,jobs,directory,_,store,pubs,old,request=setup(tmp_path)
    original=files(pubs.root/old['id']);selected=jobs.selection(request['space_id']);base=jobs.model(request['base_candidate_id'])
    created=relate(jobs,store,RelationRequest(**request));model=jobs.model(created['id'])
    assert jobs.selection(request['space_id'])==selected
    assert (model.root/'spatial.npz').read_bytes()==(base.root/'spatial.npz').read_bytes()
    query=model.objects('cabinet-a');assert query['profile']=='cospace.preview-object-query/0.3'
    assert len(query['relations'])==1 and query['relations'][0]['confirmation']=='unverified'
    query['relations'][0]['note']='mutated response';assert model.objects('cabinet-a')['relations'][0]['note']!='mutated response'
    report=compare(jobs,CompareRequest(space_id=request['space_id'],candidate_id=created['id'],expected_revision=selected['revision']))
    assert len(report['relations']['added'])==2 and report['ontology']['changed']
    selected=confirm(jobs,ReviewRequest(space_id=request['space_id'],candidate_id=created['id'],expected_revision=selected['revision'],
        comparison_sha256=report['comparison_sha256'],acknowledge_unverified=True,note='关系流程核对，非现场确认'))
    new=pubs.publish(created['id'],selected['revision'],request['space_id']);raw=export_bundle(new,pubs.read(new['id'])[1])
    offline=OfflinePreview(raw,new['id'],sha(raw))
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=store)) as client:
        online=client.get(f"/publications/{new['id']}/api/objects").json()
        assert offline.objects()==online
        assert offline.objects('cabinet-a')==client.get(f"/publications/{new['id']}/api/objects/cabinet-a").json()
        info=client.get(f"/publications/{new['id']}/offline.json").json()
        assert info['profile']=='cospace.preview-offline/0.4' and 'relations.json' in info['contents']
    diff=compare_publications(pubs,PublicationCompareRequest(space_id=request['space_id'],base_publication_id=old['id'],target_publication_id=new['id']))
    assert len(diff['changes']['relations']['added'])==2
    assert files(pubs.root/old['id'])==original and 'relations' not in pubs.read(old['id'])[1].objects()
    schema=json.loads(Path('contracts/schemas/preview-relations-v0.1.schema.json').read_bytes());Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema);validator.validate(request);validator.validate(model.relation_snapshot)

@pytest.mark.parametrize('kind,code',[
    ('unknown','unknown_relation_type'),('missing','relation_endpoint_missing'),('self','relation_self_link'),
    ('direction','relation_endpoint_type'),('id','duplicate_relation_id'),('inverse','duplicate_relation_assertion'),
    ('symmetric','duplicate_relation_assertion'),('parents','relation_multiple_parents'),('cycle','relation_containment_cycle')])
def test_invalid_relations_leave_no_candidate(tmp_path,kind,code):
    _,jobs,_,_,store,_,_,request=setup(tmp_path);r=request['relations']
    if kind=='unknown':r[0]['type_id']='unknown'
    elif kind=='missing':r[0]['target_id']='foreign-object'
    elif kind=='self':r[0]['target_id']='room-a'
    elif kind=='direction':r[0].update(source_id='cabinet-a',target_id='room-a')
    elif kind=='id':r[1]['relation_id']=r[0]['relation_id']
    elif kind=='inverse':r.append(relation('inverse','located_in','cabinet-a','room-a'))
    elif kind=='symmetric':r.append(relation('reverse','connected_to','corridor-a','room-a'))
    elif kind=='parents':r.append(relation('other-parent','located_in','cabinet-a','room-b'))
    elif kind=='cycle':r.extend([relation('nested','contains','room-a','room-b'),relation('cycle','located_in','room-a','room-b')])
    before=files(jobs.root)
    with pytest.raises(ObjectRulesFailed) as exc:relate(jobs,store,RelationRequest(**request))
    assert code in {i['code'] for i in exc.value.report['issues']} and files(jobs.root)==before

@pytest.mark.parametrize('kind',['scope','base_hash','ontology_hash','no_semantics','old_ontology'])
def test_fixed_reference_failure_no_candidate(tmp_path,kind):
    _,jobs,_,spaces,store,_,_,r=setup(tmp_path)
    if kind=='scope':r['space_id']=spaces[1]['id']
    elif kind=='base_hash':r['base_manifest_sha256']='0'*64
    elif kind=='ontology_hash':r['ontology_ref']['sha256']='0'*64
    elif kind=='no_semantics':r.update(base_candidate_id='build-one',base_manifest_sha256=digest(jobs.root/'build-one/output/model.json'))
    else:r['ontology_ref']=jobs.model(r['base_candidate_id']).semantic_snapshot['ontology_ref']
    before=files(jobs.root)
    with pytest.raises(ValueError):relate(jobs,store,RelationRequest(**r))
    assert files(jobs.root)==before

def test_relation_edit_remove_and_object_revision_preservation(tmp_path):
    _,jobs,_,_,store,_,_,r=setup(tmp_path)
    created=relate(jobs,store,RelationRequest(**r));base=jobs.model(created['id'])
    request=r|{'base_candidate_id':created['id'],'base_manifest_sha256':digest(base.root/'model.json')}
    changed=deepcopy(request);changed['relations'][0]['note']='修订人工说明'
    revised=relate(jobs,store,RelationRequest(**changed));from packages.construction.preview_changes import compare_models
    diff=compare_models(base,jobs.model(revised['id']),0,{k:base.manifest[k] for k in ('space_id','project_id')})
    assert len(diff['relations']['modified'])==1
    removed=relate(jobs,store,RelationRequest(**(request|{'relations':[]})))
    assert jobs.model(removed['id']).objects()['relations']==[]
    objects=[{k:o[k] for k in ('object_id','type_id','properties')}|{'point_index':o['evidence']['point_index']} for o in base.semantic_snapshot['objects']]
    body={k:v for k,v in request.items() if k!='relations'};body['objects']=objects
    objects[0]['properties']['name']='改名不改变关系'
    kept=annotate(jobs,store,SemanticRequest(**body));assert len(jobs.model(kept['id']).objects()['relations'])==2
    body['objects']=[o for o in objects if o['object_id']!='cabinet-a']
    pruned=annotate(jobs,store,SemanticRequest(**body));assert len(jobs.model(pruned['id']).objects()['relations'])==1
    body['objects']=deepcopy(objects);body['objects'][0]['type_id']='cabinet'
    before=files(jobs.root)
    with pytest.raises(ObjectRulesFailed):annotate(jobs,store,SemanticRequest(**body))
    assert files(jobs.root)==before

@pytest.mark.parametrize('kind',['objects_hash','ontology_ref','scope','count','self','confirmed','orphan'])
def test_rehashed_invalid_snapshot_rejected(tmp_path,kind):
    _,jobs,_,_,store,_,_,request=setup(tmp_path);created=relate(jobs,store,RelationRequest(**request));model=jobs.model(created['id'])
    path=model.root/'relations.json';doc=json.loads(path.read_bytes());manifest=deepcopy(model.manifest)
    if kind=='objects_hash':doc['objects_sha256']='0'*64
    elif kind=='ontology_ref':doc['ontology_ref']['version']='0.1.0'
    elif kind=='scope':doc['space_id']='space-'+'0'*16
    elif kind=='count':manifest['object_relations']['relation_count']=100
    elif kind=='self':doc['relations'][0]['target_id']=doc['relations'][0]['source_id']
    elif kind=='confirmed':doc['relations'][0]['confirmation']='confirmed'
    else:del manifest['object_relations']
    path.write_text(json.dumps(doc),encoding='utf-8');manifest['members']['relations.json']={'sha256':digest(path),'bytes':path.stat().st_size}
    (model.root/'model.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError):PreviewModel(model.root)

def test_business_bindings_and_offline_restore_survive_relation_upgrade(tmp_path,monkeypatch):
    from test_preview_business import setup as business_setup
    from packages.construction.preview_business import associate
    from packages.spatial.preview_business import BusinessRequest
    from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
    _,jobs,_,_,store,ledger,_,_,record,request=business_setup(tmp_path)
    business=associate(jobs,store,ledger,BusinessRequest(**request));base=jobs.model(business['id']);rule=store.register(SEED)
    objects=[{k:o[k] for k in ('object_id','type_id','properties')}|{'point_index':0} for o in base.semantic_snapshot['objects']]
    objects.append({'object_id':'cabinet-a','type_id':'cabinet','properties':{'name':'待核实柜'},'point_index':0})
    base_record=annotate(jobs,store,SemanticRequest(space_id=request['space_id'],base_candidate_id=business['id'],base_manifest_sha256=digest(base.root/'model.json'),ontology_ref={k:rule[k] for k in ('ontology_id','version','sha256')},objects=objects))
    base=jobs.model(base_record['id']);linked=relate(jobs,store,RelationRequest(space_id=request['space_id'],base_candidate_id=base_record['id'],base_manifest_sha256=digest(base.root/'model.json'),ontology_ref=base.semantic_snapshot['ontology_ref'],relations=[relation(source='object-001')]))
    pubs=PreviewPublications(jobs);selected=jobs.select(linked['id'],1,request['space_id']);pub=pubs.publish(linked['id'],selected['revision'],request['space_id'])
    raw=export_bundle(pub,pubs.read(pub['id'])[1]);expected=OfflinePreview(raw,pub['id'],sha(raw)).objects()
    assert expected['objects'][0]['business_links'][0]['ref']==record['ref']
    with zipfile.ZipFile(io.BytesIO(raw)) as z:assert {'relations.json','business.json'}<=set(z.namelist())
    # Install/restore from a library after its source ZIP and live ledger are gone.
    library=PersistentPreviewConsumer.initialize(tmp_path/'consumer',request['space_id'])
    package=tmp_path/'bundle.zip';package.write_bytes(raw);library.install(package,pub['id'],sha(raw));expected=library.activate(pub['id'],sha(raw),0).objects()
    package.unlink();(ledger.root/(record['ref']['record_id']+'.json')).unlink()
    import socket
    monkeypatch.setattr(socket,'socket',lambda *a,**k:(_ for _ in ()).throw(AssertionError('network forbidden')))
    restored=PersistentPreviewConsumer(tmp_path/'consumer');assert restored.restore(pub['id'],sha(raw),1).objects()==expected

def test_api_draft_validation_and_strict_fields(tmp_path):
    initial,jobs,directory,_,store,_,_,r=setup(tmp_path);base=jobs.model(r['base_candidate_id'])
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=store)) as client:
        endpoint=f"/api/ontologies/{r['ontology_ref']['ontology_id']}/{r['ontology_ref']['version']}/validate"
        body={'sha256':r['ontology_ref']['sha256'],'objects':[{k:o[k] for k in ('object_id','type_id','properties')} for o in base.semantic_snapshot['objects']],'relations':deepcopy(r['relations'])}
        before=files(jobs.root)
        report=client.post(endpoint,json=body).json();assert report['status']=='passed' and report['saved'] is False and report['relation_count']==2
        body['relations'].append(relation('bad','located_in','cabinet-a','room-b'))
        report=client.post(endpoint,json=body).json();assert report['status']=='failed' and report['issues'][0]['path'].startswith('/relations')
        assert files(jobs.root)==before
        assert client.post('/api/relation-candidates',json=r,headers={'Origin':'https://bad.example'}).status_code==403
        assert client.post('/api/relation-candidates',json=r|{'auto_publish':True}).status_code==422
        assert client.post('/api/relation-candidates',json=r|{'relations':[r['relations'][0]|{'confirmation':'confirmed'}]}).status_code==422
        assert client.post('/api/relation-candidates',json=r|{'relations':[r['relations'][0]|{'note':' '}]}).status_code==422
        assert client.post('/api/relation-candidates',json=r).status_code==201
