import pytest
from test_scene_ontology_links import source, command, property_command, publish_core
from packages.service.scene_ontology_links import SceneOntologyLinks, SceneLinkError


def relation_source():
    return {**source(), 'objects': source()['objects'] + [{'object_id':'room','properties':{'name':'legacy room'}}],
            'relations':[{'relation_id':'legacy:rel.1','source_id':'cabinet','target_id':'room','type_id':'legacy-location','note':'not verified'}]}


def mapping(reference, **changes):
    return {'action':'relation_set','space_id':'scene-a','candidate_id':'build-one','source_sha256':'a'*64,
            'relation_id':'legacy:rel.1','expected_revision':4,'request_id':'e'*32,'reference':reference,
            'definition_id':'located_in','direction':'forward','valid_time':{'start':'2026-11-20T00:00:00Z','end':None},
            'evidence_note':'manual statement pending field verification', **changes}


def seeded(root, room_type='spatial_region'):
    service=SceneOntologyLinks(root,'workspace','engineer',None)
    ref=publish_core(root)
    src=relation_source()
    service.change(src,command(ref))
    service.change(src,property_command())
    service.change(src,command(ref,object_id='room',concept_id=room_type,request_id='c'*32,expected_revision=2))
    service.change(src,property_command(object_id='room',request_id='d'*32,expected_revision=3))
    return service,src,ref


def test_mapping_fixed_direction_deterministic_noop_and_reference_guard(tmp_path):
    service,src,ref=seeded(tmp_path)
    assert service.read(src)['relation_report']['diagnostics'][0]['code']=='no_mapped_relations'
    body=mapping(ref)
    saved=service.change(src,body)
    assert saved['revision']==5
    assert service.change(src,body)==saved
    view=service.read(src)
    report=view['relation_report']
    assert report['valid']
    assert report['relations_checked']
    assert not report['geometry_checked']
    assert report['unmapped_count']==0
    assert report==service.read(src)['relation_report']
    assert view['relation_links'][0]['source_id']=='cabinet'
    assert view['relation_links'][0]['epistemic_status']=='reported'
    assert view['relation_links'][0]['linked_by']=='engineer'
    assert not service.change(src,mapping(ref,expected_revision=5,request_id='f'*32))['changed']
    assert report==service.read(src)['relation_report']
    for action in ('remove','set'):
        request=command(ref,action=action,expected_revision=5,request_id='1'*32)
        if action=='remove':
            del request['reference'],request['concept_id']
        else:
            request.update(concept_id='system',reset_properties=True)
        with pytest.raises(SceneLinkError,match='link_relations_present'):
            service.change(src,request)
    # Attribute updates retain relation mappings and revalidate combined set.
    service.change(src,property_command(properties={'name':{'value':42}},expected_revision=5,request_id='2'*32))
    assert len(service.read(src)['relation_links'])==1
    assert not service.read(src)['relation_report']['valid']
    remove=mapping(ref,action='relation_remove',expected_revision=6,request_id='3'*32)
    for key in ('reference','definition_id','valid_time','evidence_note','direction'):
        del remove[key]
    assert service.change(src,remove)['revision']==7
    assert not service.read(src)['relation_links']
    assert service.read(src)['relations']==src['relations']
    assert service.change(src,remove)['revision']==7
    assert not service.change(src,{**remove,'expected_revision':7,'request_id':'4'*32})['changed']


@pytest.mark.parametrize('changes,code', [
    ({'definition_id':'member_of'},'endpoint_type_mismatch'),
    ({'valid_time':{'start':'bad','end':None}},'schema_invalid'),
    ({'valid_time':{'start':'2026-11-21T00:00:00Z','end':'2026-11-20T00:00:00Z'}},'invalid_interval'),
])
def test_invalid_relation_drafts_saved_with_diagnostics(tmp_path,changes,code):
    service,src,ref=seeded(tmp_path)
    assert service.change(src,mapping(ref,**changes))['revision']==5
    report=service.read(src)['relation_report']
    assert not report['valid']
    assert any(issue['code']==code for issue in report['diagnostics'])
    assert not report['relations'][0]['valid']


@pytest.mark.parametrize('field', ['reference','definition_id','evidence_note','valid_time','direction'])
def test_relation_request_missing_fields_rejected(tmp_path,field):
    service=SceneOntologyLinks(tmp_path,'workspace','engineer',None)
    body=mapping({})
    del body[field]
    with pytest.raises(SceneLinkError,match='invalid_link_request'):
        service.change(relation_source(),body)


def test_relation_endpoints_must_be_linked_and_legacy_ids_not_inferred(tmp_path):
    service=SceneOntologyLinks(tmp_path,'workspace','engineer',None)
    ref=publish_core(tmp_path)
    with pytest.raises(SceneLinkError,match='relation_endpoints_unlinked'):
        service.change(relation_source(),mapping(ref,expected_revision=0))
    with pytest.raises(SceneLinkError,match='relation_not_found'):
        service.change(relation_source(),mapping(ref,relation_id='missing',expected_revision=0))
    with pytest.raises(SceneLinkError,match='relation_definition_not_found'):
        service.change(relation_source(),mapping(ref,definition_id='legacy_location',expected_revision=0))



def test_relation_conflicting_fixed_closures_and_cas(tmp_path):
    service,src,ref=seeded(tmp_path)
    newer=publish_core(tmp_path,version='0.2.0',revision=1,base=ref)
    service.change(src,mapping(newer))
    report=service.read(src)['relation_report']
    assert not report['valid']
    assert report['diagnostics'][0]['code']=='definition_version_conflict'
    with pytest.raises(SceneLinkError,match='link_revision_changed'):
        service.change(src,mapping(ref,request_id='f'*32))
    with pytest.raises(SceneLinkError,match='link_request_conflict'):
        service.change(src,mapping(ref))
    with pytest.raises(SceneLinkError,match='link_source_changed'):
        service.change(src,mapping(ref,source_sha256='b'*64))


@pytest.mark.parametrize('changes', [
    {'valid_time':None}, {'evidence_note':''}, {'valid_time':{'start':'now'}},
    {'actor':'forged'}, {'epistemic_status':'corroborated'}, {'source_id':'room'},
    {'expected_revision':True},
])
def test_relation_requests_reject_forged_or_malformed_input(tmp_path,changes):
    body=mapping({},**changes)
    service=SceneOntologyLinks(tmp_path,'workspace','engineer',None)
    with pytest.raises(SceneLinkError,match='invalid_link_request'):
        service.change(relation_source(),body)



def test_direction_reversal_is_explicit_and_original_relation_unchanged(tmp_path):
    service,src,ref=seeded(tmp_path)
    service.change(src,mapping(ref,direction='reverse'))
    view=service.read(src)
    assert view['relation_links'][0]['source_id']=='room'
    assert view['relations'][0]['source_id']=='cabinet'
    assert not view['relation_report']['valid']
    assert any(issue['code']=='endpoint_type_mismatch' for issue in view['relation_report']['diagnostics'])
    service.change(src,mapping(ref,expected_revision=5,request_id='f'*32))
    assert service.read(src)['relation_report']['valid']
