from copy import deepcopy
import io
import json
from pathlib import Path
import zipfile
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from test_preview_objects import fixture
from packages.construction.preview_semantics import annotate
from packages.construction.preview_business import associate
from packages.construction.preview_model import PreviewModel,digest
from packages.construction.preview_changes import CompareRequest,ReviewRequest,compare,confirm
from packages.service.preview_publications import PreviewPublications
from packages.service.preview_publication_changes import compare_publications,PublicationCompareRequest
from packages.spatial.preview_objects import SemanticRequest
from packages.spatial.preview_business import LedgerDraft,BusinessRequest
from packages.data.preview_ledger import PreviewLedger
from packages.views.agent.preview_offline import OfflinePreview,export_bundle,sha
from packages.views.agent.preview_consumer import PreviewConsumer
from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
from experiments.scripts.serve_nyu_flow_preview import create_app


def setup(tmp_path):
    initial,jobs,directory,spaces,ontologies,body=fixture(tmp_path)
    base=annotate(jobs,ontologies,SemanticRequest(**body))
    jobs.select(base['id'],0,body['space_id'])
    ledger=PreviewLedger(tmp_path/'ledger',directory)
    draft={'space_id':body['space_id'],'source_system':'sample-assets','external_id':'asset-001','version':'1','title':'流程测试台账 · 待核实','fields':{'asset_code':'TEST-001'}}
    registered=ledger.register(LedgerDraft(**draft))
    request={'space_id':body['space_id'],'base_candidate_id':base['id'],
        'base_manifest_sha256':digest(jobs.root/base['id']/'output/model.json'),
        'bindings':[{'object_id':'object-001','ledger_ref':registered['ref']}]}
    return initial,jobs,directory,spaces,ontologies,ledger,base,draft,registered,request


def files(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_immutable_registration_duplicate_and_version_conflict(tmp_path):
    _,_,_,_,_,ledger,_,draft,record,_=setup(tmp_path)
    assert not ledger.register(LedgerDraft(**draft))['created']
    before=files(ledger.root)
    with pytest.raises(ValueError,match='version_conflict'):ledger.register(LedgerDraft(**(draft|{'title':'changed'})))
    assert files(ledger.root)==before
    new=ledger.register(LedgerDraft(**(draft|{'version':'2','title':'next version'})))
    assert new['ref']!=record['ref'] and ledger.read(record['ref']['record_id'],record['ref']['sha256'])['record']==record['record']


def test_bind_select_publish_compare_and_offline_keep_frozen_ledger(tmp_path):
    initial,jobs,directory,_,ontologies,ledger,base,draft,record,request=setup(tmp_path)
    pubs=PreviewPublications(jobs);old=pubs.publish(base['id'],1,request['space_id']);original=files(pubs.root/old['id'])
    created=associate(jobs,ontologies,ledger,BusinessRequest(**request))
    assert jobs.selection(request['space_id'])['candidate_id']==base['id']
    model=jobs.model(created['id']);links=model.objects('object-001')['objects'][0]['business_links']
    assert links==[{'ref':record['ref'],'record':record['record']}]
    assert model.objects()['profile']=='cospace.preview-object-query/0.2'
    assert (model.root/'spatial.npz').read_bytes()==(jobs.root/base['id']/'output/spatial.npz').read_bytes()
    report=compare(jobs,CompareRequest(space_id=request['space_id'],candidate_id=created['id'],expected_revision=1))
    assert report['business']['added']==request['bindings'] and report['objects']['modified']==[]
    confirm(jobs,ReviewRequest(space_id=request['space_id'],candidate_id=created['id'],expected_revision=1,
        comparison_sha256=report['comparison_sha256'],note='本机测试绑定，待核实',acknowledge_unverified=True))
    publication=pubs.publish(created['id'],2,request['space_id'])
    result=compare_publications(pubs,PublicationCompareRequest(space_id=request['space_id'],base_publication_id=old['id'],target_publication_id=publication['id']))
    assert result['changes']['business']['added']==request['bindings']
    raw=export_bundle(*pubs.read(publication['id']));offline=OfflinePreview(raw,publication['id'],sha(raw))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert json.loads(archive.read('package.json'))['profile']=='cospace.preview-offline/0.3'
        assert 'business.json' in archive.namelist()
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies,ledger=ledger)) as client:
        online=client.get(publication['preview_url']+'api/objects/object-001').json()
        assert online==offline.objects('object-001')
        info=client.get(publication['preview_url']+'offline.json').json()
        assert info['profile']=='cospace.preview-offline/0.3' and 'business.json' in info['contents']
    # The frozen copy remains usable without the live ledger directory.
    (ledger.root/(record['ref']['record_id']+'.json')).unlink()
    ledger.register(LedgerDraft(**(draft|{'version':'2','title':'new external title'})))
    assert pubs.read(publication['id'])[1].objects('object-001')['objects'][0]['business_links']==links
    path=tmp_path/'offline.zip';path.write_bytes(raw);consumer=PreviewConsumer()
    assert consumer.activate(path,publication['id'],sha(raw),0).objects('object-001')['objects'][0]['business_links']==links
    assert files(pubs.root/old['id'])==original and 'business_links' not in pubs.read(old['id'])[1].objects()['objects'][0]


@pytest.mark.parametrize('kind',['space','object','hash','duplicate','stale','no_semantics'])
def test_invalid_binding_creates_no_candidate(tmp_path,kind):
    _,jobs,_,spaces,ontologies,ledger,_,_,_,request=setup(tmp_path)
    body=deepcopy(request)
    if kind=='space':body['space_id']=spaces[1]['id']
    elif kind=='object':body['bindings'][0]['object_id']='missing-object'
    elif kind=='hash':body['bindings'][0]['ledger_ref']['sha256']='0'*64
    elif kind=='duplicate':body['bindings']*=2
    elif kind=='stale':body['base_manifest_sha256']='0'*64
    else:
        body.update(base_candidate_id='build-one',base_manifest_sha256=digest(jobs.root/'build-one/output/model.json'))
    before=files(jobs.root)
    with pytest.raises(ValueError):associate(jobs,ontologies,ledger,BusinessRequest(**body))
    assert files(jobs.root)==before


def test_cross_space_ledger_ref_rejected(tmp_path):
    _,jobs,_,spaces,ontologies,ledger,_,draft,_,request=setup(tmp_path)
    foreign=ledger.register(LedgerDraft(**(draft|{'space_id':spaces[1]['id']})))
    request['bindings'][0]['ledger_ref']=foreign['ref']
    before=files(jobs.root)
    with pytest.raises(ValueError,match='ownership'):associate(jobs,ontologies,ledger,BusinessRequest(**request))
    assert files(jobs.root)==before


def test_frozen_base_record_can_be_preserved_when_live_registry_is_missing(tmp_path):
    _,jobs,_,_,ontologies,ledger,_,_,record,request=setup(tmp_path)
    first=associate(jobs,ontologies,ledger,BusinessRequest(**request));model=jobs.model(first['id'])
    (ledger.root/(record['ref']['record_id']+'.json')).unlink()
    request.update(base_candidate_id=first['id'],base_manifest_sha256=digest(model.root/'model.json'))
    next_record=associate(jobs,ontologies,ledger,BusinessRequest(**request))
    assert jobs.model(next_record['id']).objects()['objects'][0]['business_links'][0]['ref']==record['ref']


def test_empty_binding_set_reported_as_removal_and_fixed_old_package_unchanged(tmp_path):
    _,jobs,_,_,ontologies,ledger,_,_,_,request=setup(tmp_path)
    first=associate(jobs,ontologies,ledger,BusinessRequest(**request));jobs.select(first['id'],1,request['space_id'])
    pubs=PreviewPublications(jobs);old=pubs.publish(first['id'],2,request['space_id']);raw=export_bundle(*pubs.read(old['id']))
    request.update(base_candidate_id=first['id'],base_manifest_sha256=digest(jobs.root/first['id']/'output/model.json'),bindings=[])
    cleared=associate(jobs,ontologies,ledger,BusinessRequest(**request))
    report=compare(jobs,CompareRequest(space_id=request['space_id'],candidate_id=cleared['id'],expected_revision=2))
    assert len(report['business']['removed'])==1 and not report['business']['added']
    assert export_bundle(*pubs.read(old['id']))==raw


def test_business_package_persists_and_restores_without_network_or_registry(tmp_path,monkeypatch):
    _,jobs,_,_,ontologies,ledger,_,_,record,request=setup(tmp_path)
    first=associate(jobs,ontologies,ledger,BusinessRequest(**request));jobs.select(first['id'],1,request['space_id'])
    pubs=PreviewPublications(jobs);publication=pubs.publish(first['id'],2,request['space_id'])
    raw=export_bundle(*pubs.read(publication['id']));path=tmp_path/'download.zip';path.write_bytes(raw)
    store=PersistentPreviewConsumer.initialize(tmp_path/'consumer',request['space_id']);store.install(path,publication['id'],sha(raw))
    expected=store.activate(publication['id'],sha(raw),0).objects('object-001')
    path.unlink();(ledger.root/(record['ref']['record_id']+'.json')).unlink()
    import socket
    monkeypatch.setattr(socket,'socket',lambda *a,**k:pytest.fail('offline restore must not use network'))
    restarted=PersistentPreviewConsumer(store.root)
    assert restarted.restore(publication['id'],sha(raw),1).objects('object-001')==expected


def test_rebind_unbind_and_object_edit_preserve_or_remove_only_relevant_links(tmp_path):
    _,jobs,_,_,ontologies,ledger,_,draft,record,request=setup(tmp_path)
    first=associate(jobs,ontologies,ledger,BusinessRequest(**request));model=jobs.model(first['id'])
    revised=ledger.register(LedgerDraft(**(draft|{'version':'2','title':'new title'})))
    update=request|{'base_candidate_id':first['id'],'base_manifest_sha256':digest(model.root/'model.json')}
    rebound=associate(jobs,ontologies,ledger,BusinessRequest(**(update|{'bindings':[{'object_id':'object-001','ledger_ref':revised['ref']}]})))
    assert jobs.model(rebound['id']).objects()['objects'][0]['business_links'][0]['record']['version']=='2'
    cleared=associate(jobs,ontologies,ledger,BusinessRequest(**(update|{'bindings':[]})))
    assert jobs.model(cleared['id']).objects()['objects'][0]['business_links']==[]
    doc=model.semantic_snapshot
    edit=SemanticRequest(space_id=request['space_id'],base_candidate_id=first['id'],base_manifest_sha256=digest(model.root/'model.json'),
        ontology_ref=doc['ontology_ref'],objects=[{'object_id':'object-001','type_id':'room','properties':{'name':'edited'},'point_index':0}])
    edited=annotate(jobs,ontologies,edit)
    assert jobs.model(edited['id']).objects()['objects'][0]['business_links'][0]['ref']==record['ref']
    changed=edit.model_copy(update={'objects':[edit.objects[0].model_copy(update={'object_id':'new-object'})]})
    replaced=annotate(jobs,ontologies,changed)
    assert jobs.model(replaced['id']).business_snapshot['bindings']==[]


@pytest.mark.parametrize('kind',['object','record','digest','scope','unused'])
def test_rehashed_malformed_business_snapshot_rejected(tmp_path,kind):
    _,jobs,_,_,ontologies,ledger,_,_,_,request=setup(tmp_path)
    created=associate(jobs,ontologies,ledger,BusinessRequest(**request));root=jobs.root/created['id']/'output'
    path=root/'business.json';doc=json.loads(path.read_bytes())
    if kind=='object':doc['bindings'][0]['object_id']='not-in-model'
    elif kind=='record':doc['records'][0]['record']['title']='tampered'
    elif kind=='digest':doc['objects_sha256']='0'*64
    elif kind=='scope':doc['project_id']='project-'+'0'*16
    else:doc['bindings']=[]
    path.write_text(json.dumps(doc));manifest=json.loads((root/'model.json').read_bytes())
    manifest['members']['business.json']={'sha256':digest(path),'bytes':path.stat().st_size}
    (root/'model.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):PreviewModel(root)


def test_api_scope_origin_strict_schema_and_duplicate_registration(tmp_path):
    initial,jobs,directory,spaces,ontologies,ledger,_,draft,_,request=setup(tmp_path)
    schema=json.loads(Path('contracts/schemas/preview-business-v0.1.schema.json').read_bytes());validator=Draft202012Validator(schema)
    Draft202012Validator.check_schema(schema);validator.validate(draft);validator.validate(request)
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=ontologies,ledger=ledger)) as client:
        assert len(client.get('/api/ledger',params={'space_id':request['space_id']}).json()['records'])==1
        assert client.get('/api/ledger',params={'space_id':spaces[1]['id']}).json()['records']==[]
        assert client.get('/api/ledger').status_code==422
        assert client.post('/api/ledger',json=draft).json()['created'] is False
        assert client.post('/api/ledger',json=draft,headers={'Origin':'https://bad.example'}).status_code==403
        assert client.post('/api/ledger',json=draft|{'title':' '}).status_code==422
        assert client.post('/api/ledger',json=draft|{'fields':{'unknown':'value'}}).status_code==422
        assert client.post('/api/business-candidates',json=request|{'confirmation':'verified'}).status_code==422
        response=client.post('/api/business-candidates',json=request);assert response.status_code==201,response.text
        validator.validate(jobs.model(response.json()['id']).business_snapshot)
