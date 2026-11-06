import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from packages.ontology.preview_versions import PreviewOntologies
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_real_model_preview import make_preview

SEED=Path('configs/ontology/indoor-equipment-v0.1.json')


def fixture(tmp_path):
    store=PreviewOntologies(tmp_path/'ontologies'); record=store.register(SEED)
    return store,record


def draft(**changes):
    return {'object_id':'draft-1','type_id':'cabinet','properties':{'name':'待确认柜体'},**changes}


def test_sealed_version_persists_and_source_changes_cannot_replace_it(tmp_path):
    source=tmp_path/'source.json'; source.write_bytes(SEED.read_bytes())
    store,record=fixture(tmp_path)
    assert store.register(source)==record
    value=json.loads(source.read_bytes()); value['types']['cabinet']['title']='renamed'
    source.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError,match='already_sealed'): store.register(source)
    restarted=PreviewOntologies(store.root)
    assert restarted.read(record['ontology_id'],record['version'],record['sha256'])[0]==record
    assert restarted.list()==[record]
    returned=restarted.read(record['ontology_id'],record['version'])[1]
    returned['types'].clear()
    assert len(restarted.read(record['ontology_id'],record['version'])[1]['types'])==4
    assert not list(store.root.glob('.pending-*'))


def test_new_version_does_not_change_old_rules_or_reference(tmp_path):
    store,old=fixture(tmp_path)
    value=json.loads(SEED.read_bytes()); value['version']='0.2.0'
    value['types']['cabinet']['properties']['asset_code']['required']=True
    source=tmp_path/'v2.json'; source.write_text(json.dumps(value),encoding='utf-8')
    new=store.register(source)
    assert len(store.list())==2 and new['sha256']!=old['sha256']
    assert store.inspect(old['ontology_id'],old['version'],old['sha256'],[draft()])['status']=='passed'
    changed=store.inspect(new['ontology_id'],new['version'],new['sha256'],[draft()])
    assert changed['issues'][0]['path']=='/objects/0/properties/asset_code'
    with pytest.raises(ValueError,match='reference_mismatch'):
        store.inspect(old['ontology_id'],old['version'],new['sha256'],[draft()])


@pytest.mark.parametrize('change',[
    lambda v:v['types']['cabinet']['properties']['name'].update(type='number'),
    lambda v:v['types']['cabinet']['properties']['name'].update(required='yes'),
    lambda v:v['types']['cabinet']['properties']['name'].update(min_length=200,max_length=1),
    lambda v:v.update(extra=True),
])
def test_invalid_rule_configuration_refused(tmp_path,change):
    value=json.loads(SEED.read_bytes()); change(value)
    source=tmp_path/'bad.json'; source.write_text(json.dumps(value),encoding='utf-8')
    store=PreviewOntologies(tmp_path/'store')
    with pytest.raises(ValueError,match='definition_invalid'): store.register(source)
    assert store.list()==[]


@pytest.mark.parametrize(('obj','code','path'),[
    (draft(type_id='unknown'),'unknown_type','/objects/0/type_id'),
    (draft(properties={}), 'missing_required_property','/objects/0/properties/name'),
    (draft(properties={'name':12}), 'invalid_property_type','/objects/0/properties/name'),
    (draft(properties={'name':'   '}), 'invalid_property_length','/objects/0/properties/name'),
    (draft(properties={'name':'x','a/b~c':True}), 'undefined_property','/objects/0/properties/a~1b~0c'),
    (draft(confirmation='confirmed'), 'undefined_object_field','/objects/0/confirmation'),
    (draft(object_id=''), 'invalid_object_id','/objects/0/object_id'),
    (draft(properties=[]), 'invalid_properties','/objects/0/properties'),
])
def test_diagnostics_locate_object_and_field_without_writes(tmp_path,obj,code,path):
    store,record=fixture(tmp_path)
    before={str(p.relative_to(store.root)):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    result=store.inspect(record['ontology_id'],record['version'],record['sha256'],[obj])
    assert result['status']=='failed' and any(i['code']==code and i['path']==path for i in result['issues'])
    assert result['saved'] is False and result['semantic_confirmation']=='not_attempted' and result['robot_ready'] is False
    assert before=={str(p.relative_to(store.root)):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}


def test_duplicate_ids_rejected_and_valid_rules_do_not_confirm_objects(tmp_path):
    store,record=fixture(tmp_path)
    result=store.inspect(record['ontology_id'],record['version'],record['sha256'],[draft(),draft()])
    assert result['issues'][0]['code']=='duplicate_object_id'
    assert result['issues'][0]['path']=='/objects/1/object_id'
    good=store.inspect(record['ontology_id'],record['version'],record['sha256'],[draft()])
    assert good['status']=='passed' and good['saved'] is False


@pytest.mark.parametrize('member',['definition.json','record.json'])
def test_tampered_snapshot_blocks_read_and_validation(tmp_path,member):
    store,record=fixture(tmp_path)
    path=store.path(record['ontology_id'],record['version'])/member
    path.write_bytes(b'[]')
    with pytest.raises(ValueError,match='integrity_changed'):
        store.read(record['ontology_id'],record['version'],record['sha256'])
    with pytest.raises(ValueError,match='integrity_changed'):
        store.inspect(record['ontology_id'],record['version'],record['sha256'],[draft()])


def test_api_requires_fixed_reference_and_does_not_change_model(tmp_path):
    store,record=fixture(tmp_path); root=tmp_path/'model'; root.mkdir(); make_preview(root)
    before={p.name:p.read_bytes() for p in root.iterdir()}
    route=f"/api/ontologies/{record['ontology_id']}/{record['version']}"
    with TestClient(create_app(root,ontologies=store)) as client:
        assert client.get('/api/ontologies').json()['ontologies']==[record]
        assert client.get(route).status_code==422
        assert client.get(route+'?sha256='+record['sha256']).json()['definition']['types']['cabinet']
        assert client.get(route+'?sha256='+'0'*64).status_code==409
        assert client.get('/api/ontologies/missing/0.1.0?sha256='+'0'*64).status_code==404
        body={'sha256':record['sha256'],'objects':[draft()]}
        assert client.post(route+'/validate',json=body,headers={'Origin':'https://example.com'}).status_code==403
        assert client.post(route+'/validate',json=body|{'space_id':'invented'}).status_code==422
        assert client.post(route+'/validate',json=body|{'sha256':'0'*64}).status_code==409
        assert client.post(route+'/validate',json=body|{'objects':[]}).status_code==422
        assert client.post(route+'/validate',json=body|{'objects':[draft()]*101}).status_code==422
        assert client.post(route+'/validate',json=body).json()['status']=='passed'
        assert client.post(route+'/validate',json=body|{'objects':[draft(type_id='unknown')]}).json()['status']=='failed'
        path=store.path(record['ontology_id'],record['version'])/'definition.json'; path.write_bytes(b'{}')
        assert client.get('/api/ontologies').status_code==409
        assert client.get(route+'?sha256='+record['sha256']).status_code==409
        assert client.post(route+'/validate',json=body).status_code==409
    assert {p.name:p.read_bytes() for p in root.iterdir()}==before


def test_unconfigured_and_empty_are_distinct(tmp_path):
    root=tmp_path/'model'; root.mkdir(); make_preview(root)
    with TestClient(create_app(root)) as client:
        assert client.get('/api/ontologies').status_code==503
    with TestClient(create_app(root,ontologies=PreviewOntologies(tmp_path/'empty'))) as client:
        assert client.get('/api/ontologies').json()['ontologies']==[]
