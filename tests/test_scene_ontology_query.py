from copy import deepcopy
import pytest
from test_scene_ontology_relation_links import seeded, mapping
from test_scene_ontology_links import property_command
from packages.service.scene_ontology_links import SceneOntologyLinks, SceneLinkError


def located_source(src):
    value=deepcopy(src)
    value.update(frame_id='local-model',unit='m',axes=['x','y','z'],source_model_sha256='b'*64)
    value['objects'][0].update(anchor_m=[1.0,2.0,3.0],evidence={'kind':'model_point','member':'spatial.npz','sha256':'b'*64,'point_index':2})
    return value


def query(service,src,revision=5,**changes):
    return service.query(src,{'space_id':src['space_id'],'candidate_id':src['candidate_id'],
        'object_id':'cabinet','revision':str(revision),**changes})


def test_fixed_revision_join_survives_latest_changes_and_time_classifies(tmp_path):
    service,src,ref=seeded(tmp_path)
    src=located_source(src)
    service.change(src,mapping(ref,valid_time={'start':'2026-11-20T00:00:00Z','end':'2026-11-21T00:00:00Z'}))
    before=query(service,src)
    assert before['revision']==5
    assert before['claim']['instance_properties']['name']['value']=='manual name'
    assert before['claim']['time_state']=='not_recorded'
    assert before['model_location']['available']
    assert before['model_location']['position']==[1,2,3]
    assert not before['model_location']['geographic_location']['available']
    assert not before['model_location']['field_verified']
    assert 'bundle' not in before['claim']
    for at,state in [('2026-11-19T23:59:59Z','inactive'),('2026-11-20T00:00:00Z','active'),('2026-11-21T00:00:00Z','inactive')]:
        viewed=query(service,src,at=at)
        assert viewed['relations'][0]['time_state']==state
        assert viewed['claim']['time_state']=='not_recorded'
    service.change(src,property_command(properties={'name':{'value':'new claim'}},expected_revision=5,request_id='f'*32))
    assert query(service,src)==before
    assert query(service,src,6)['claim']['instance_properties']['name']['value']=='new claim'
    assert query(service,src,0)['claim'] is None
    with pytest.raises(SceneLinkError,match='link_revision_not_found'):
        query(service,src,7)
    other=SceneOntologyLinks(tmp_path,'other-workspace','engineer',None)
    with pytest.raises(SceneLinkError,match='link_revision_not_found'):
        query(other,src)
    with pytest.raises(SceneLinkError,match='link_source_changed'):
        query(service,{**src,'source_sha256':'c'*64})


@pytest.mark.parametrize('at',['now','2026-02-30T00:00:00Z','2026-11-20T00:00:00','2026-11-20T00:00:00+08:00',''])
def test_query_time_is_strict_utc(tmp_path,at):
    service,src,ref=seeded(tmp_path)
    with pytest.raises(SceneLinkError,match='invalid_query_time'):
        query(service,src,4,at=at)


@pytest.mark.parametrize('revision',['-1','01','latest','1.0','9999999999999999999'])
def test_query_never_falls_back_to_latest(tmp_path,revision):
    service=SceneOntologyLinks(tmp_path,'workspace','engineer',None)
    with pytest.raises(SceneLinkError,match='invalid_link_request'):
        query(service,located_source({'space_id':'scene-a','candidate_id':'build-one','source_sha256':'a'*64,'objects':[{'object_id':'cabinet','properties':{}}]}),revision)
    assert not service.path.exists()


def test_missing_anchor_and_bad_semantic_period_remain_explicit(tmp_path):
    service,src,ref=seeded(tmp_path)
    service.change(src,property_command(expected_revision=4,request_id='e'*32,valid_time={'start':'bad','end':None}))
    value=query(service,src,at='2026-11-20T00:00:00Z')
    assert not value['model_location']['available']
    assert value['claim']['time_state']=='invalid'
    assert not value['attribute_report']['valid']
    assert not value['included_in_publication']
    with service.connect() as connection:
        connection.execute('UPDATE link_snapshots SET payload=? WHERE revision=5',(b'{}',))
    with pytest.raises(SceneLinkError,match='link_store_integrity'):
        query(service,src)


@pytest.mark.parametrize('park',['research-office','manufacturing','logistics'])
def test_three_park_packages_keep_definitions_evidence_and_local_coordinates(tmp_path,park):
    import json
    from pathlib import Path
    from packages.ontology.kernel import builtin_catalog
    from packages.service.scene_ontology_links import concept_definition
    from packages.service.scene_ontology_query import query_object
    package=json.loads(Path('examples/ontology/parks',park+'.json').read_bytes())
    catalog=builtin_catalog()
    entity=next(item for item in package['entities'] if item['type'].startswith('core:'))
    module,concept=entity['type'].split(':')
    ref=next(item for item in package['definition_refs'] if item['module_id']==module)
    evidence={item['id']:item for item in package['evidence']}
    note=evidence[entity['evidence_ids'][0]]['description']
    link={'object_id':entity['id'],'reference':ref,'concept_id':concept,'bundle':catalog.export(module),
          'definition':concept_definition(catalog.export(module),ref,concept),'linked_at':package['generated_at'],
          'linked_by':'fixture','instance_properties':{key:{k:v for k,v in value.items() if k in ('value','unit','quantity')} for key,value in entity['properties'].items()},'evidence_note':note}
    if 'valid_time' in entity:
        link['instance_valid_time']=entity['valid_time']
    source={'space_id':'scene-'+park,'candidate_id':'build-one','source_sha256':'a'*64,
            'frame_id':'local-'+park,'unit':'m','source_model_sha256':'b'*64,
            'objects':[{'object_id':entity['id'],'properties':{'name':park},'anchor_m':[1,2,3],
                        'evidence':{'kind':'model_point','member':'spatial.npz','sha256':'b'*64,'point_index':0}}]}
    view=query_object(source,{'revision':1,'links':[link]},entity['id'])
    assert view['claim']['evidence_note']==note
    assert view['claim']['reference']==ref
    assert view['model_location']['frame_id']=='local-'+park
    assert not view['model_location']['geographic_location']['available']


@pytest.mark.parametrize('changes', [
    {'unit':'cm'}, {'source_model_sha256':'c'*64},
])
def test_model_point_bindings_fail_closed(tmp_path,changes):
    service,src,_=seeded(tmp_path)
    src={**located_source(src),**changes}
    location=query(service,src,4)['model_location']
    assert not location['available']
    assert not location['preview_available']
    assert 'position' not in location


def test_model_point_with_missing_axes_has_evidence_but_no_preview(tmp_path):
    service,src,_=seeded(tmp_path)
    src=located_source(src)
    del src['axes']
    location=query(service,src,4)['model_location']
    assert location['available']
    assert not location['preview_available']
    assert location['preview_reason']=='model_axes_not_recorded'
