from concurrent.futures import ThreadPoolExecutor

import pytest

from packages.ontology.kernel import builtin_catalog
from packages.ontology.kernel.authoring import AuthoringError
from packages.service.ontology_definition_workbench import DefinitionWorkbench
from packages.service.scene_ontology_links import SceneOntologyLinks, SceneLinkError


def publish_core(root, scope='workspace', version='0.1.0', revision=0, base=None):
    editor = DefinitionWorkbench(root, scope, 'editor', True).service
    reviewer = DefinitionWorkbench(root, scope, 'reviewer', True).service
    bundle = builtin_catalog().export('core')
    bundle['modules'][0]['version'] = version
    ids = iter(f'{revision * 10 + i:032x}' for i in range(1, 5))
    editor.save(scope, 'editor', next(ids), module_id='core', expected_revision=revision,
                bundle=bundle, base_reference=base)
    review = editor.submit(scope, 'editor', next(ids), module_id='core', expected_revision=revision + 1)
    reviewer.decide(scope, 'reviewer', next(ids), review_id=review['review_id'], decision='approved', reason='fixture review')
    return editor.publish(scope, 'editor', next(ids), review_id=review['review_id'], expected_revision=revision + 1)['reference']


def source():
    return {'space_id': 'scene-a', 'candidate_id': 'build-one', 'source_sha256': 'a' * 64,
            'objects': [{'object_id': 'cabinet', 'properties': {'name': '配电柜'}}]}


def command(reference, **changes):
    return {'action': 'set', 'space_id': 'scene-a', 'candidate_id': 'build-one', 'source_sha256': 'a' * 64,
            'object_id': 'cabinet', 'reference': reference, 'concept_id': 'physical_object',
            'request_id': 'a' * 32, 'expected_revision': 0, **changes}


def test_published_only_fixed_reference_and_inherited_properties(tmp_path):
    service = SceneOntologyLinks(tmp_path, 'workspace', 'engineer', None)
    assert service.read(source())['options'] == []
    ref = builtin_catalog().describe()['modules'][0]['reference']
    with pytest.raises(AuthoringError, match='release_not_found'):
        service.change(source(), command(ref))
    ref = publish_core(tmp_path)
    assert len(service.options()) == 1
    result = service.change(source(), command(ref))
    assert result['revision'] == 1
    assert service.change(source(), command(ref)) == result
    assert not service.change(source(), command(ref, request_id='b' * 32, expected_revision=1))['changed']
    snapshot = service.read(source())
    assert snapshot['revision'] == 1
    assert 'name' in snapshot['links'][0]['definition']['effective_properties']
    assert snapshot['instance_validation'] == 'attributes_checked'
    assert snapshot['included_in_publication'] is False
    newer = publish_core(tmp_path, version='0.2.0', revision=1, base=ref)
    assert len(service.options()) == 2
    assert service.read(source())['links'][0]['reference'] == ref != newer
    assert SceneOntologyLinks(tmp_path, 'other-workspace', 'engineer', None).read(source())['links'] == []
    other_source = {**source(), 'candidate_id': 'build-two'}
    assert service.read(other_source)['links'] == []


def test_concurrency_remove_and_scope_safety(tmp_path):
    service = SceneOntologyLinks(tmp_path, 'workspace', 'engineer', None)
    ref = publish_core(tmp_path)
    def attempt(request_id):
        try:
            service.change(source(), command(ref, request_id=request_id))
            return 'saved'
        except SceneLinkError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, ['a' * 32, 'b' * 32])) == ['link_revision_changed', 'saved']
    remove = command(ref, action='remove', request_id='c' * 32, expected_revision=1)
    del remove['reference'], remove['concept_id']
    assert service.change(source(), remove)['revision'] == 2
    assert service.read(source())['links'] == []
    assert service.read(source())['updated_by'] == 'engineer'
    with pytest.raises(SceneLinkError, match='link_request_conflict'):
        service.change(source(), {**remove, 'expected_revision': 2})
    for changes, code in [({'actor': 'forged'}, 'invalid_link_request'), ({'object_id': 'missing'}, 'object_not_found'),
                          ({'expected_revision': True}, 'invalid_link_request'), ({'concept_id': 'missing'}, 'concept_not_found'),
                          ({'source_sha256': 'b' * 64}, 'link_source_changed')]:
        with pytest.raises(SceneLinkError, match=code):
            service.change(source(), command(ref, **changes))


def test_corrupt_store_and_source_change_fail_closed(tmp_path):
    service = SceneOntologyLinks(tmp_path, 'workspace', 'engineer', None)
    ref = publish_core(tmp_path)
    service.change(source(), command(ref))
    with pytest.raises(SceneLinkError, match='link_source_changed'):
        service.read({**source(), 'source_sha256': 'b' * 64})
    with service.connect() as connection:
        connection.execute("UPDATE link_snapshots SET payload=?", (b'{}',))
    with pytest.raises(SceneLinkError, match='link_store_integrity'):
        service.read(source())


def test_explicit_properties_validate_and_version_change_requires_reset(tmp_path):
    service = SceneOntologyLinks(tmp_path, 'workspace', 'engineer', None)
    ref = publish_core(tmp_path)
    service.change(source(), command(ref))
    initial = service.read(source())['instance_report']
    assert not initial['valid']
    assert any(i['code'] == 'required_property' for i in initial['diagnostics'])
    properties = command(ref, action='properties', request_id='b'*32, expected_revision=1)
    del properties['reference'], properties['concept_id']
    properties.update(properties={'name': {'value': '人工声明配电柜'}}, valid_time=None, evidence_note='依据设备标牌人工录入，待现场复核')
    saved = service.change(source(), properties)
    assert saved['revision'] == 2
    assert service.change(source(), properties) == saved
    report = service.read(source())['instance_report']
    assert report['valid'] and not report['relations_checked'] and not report['geometry_checked']
    assert report['professional_review'] == 'not_performed'
    bad = {**properties, 'request_id':'c'*32, 'expected_revision':2, 'properties':{'name':{'value':42}}}
    assert service.change(source(), bad)['revision'] == 3
    assert any(i['code']=='property_type_mismatch' for i in service.read(source())['instance_report']['diagnostics'])
    ref2 = publish_core(tmp_path, version='0.2.0', revision=1, base=ref)
    upgrade = command(ref2, request_id='d'*32, expected_revision=3)
    with pytest.raises(SceneLinkError, match='link_attributes_present'):
        service.change(source(), upgrade)
    service.change(source(), {**upgrade, 'reset_properties':True})
    link = service.read(source())['links'][0]
    assert 'instance_properties' not in link
    assert link['reference'] == ref2


@pytest.mark.parametrize('changes', [
    {'properties':{'name':{'value':float('inf')}}}, {'properties':{'name':{'value':10**400}}}, {'evidence_note':''},
    {'properties':{'name':{'value':'柜','source_id':'forged'}}},
    {'properties':{'name':{'value':[]}}}, {'valid_time':{'start':'now'}},
])
def test_property_request_shape_rejects_unsafe_claims(tmp_path, changes):
    service = SceneOntologyLinks(tmp_path, 'workspace', 'engineer', None)
    body = command({}, action='properties')
    del body['reference'], body['concept_id']
    body.update(properties={}, valid_time=None, evidence_note='manual claim')
    with pytest.raises(SceneLinkError, match='invalid_link_request'):
        service.change(source(), {**body, **changes})


def property_command(**changes):
    value = command({}, action='properties', request_id='b'*32, expected_revision=1)
    del value['reference'], value['concept_id']
    return {**value, 'properties': {'name': {'value': 'manual name'}},
            'valid_time': None, 'evidence_note': 'manual source', **changes}


@pytest.mark.parametrize('field', ['properties', 'valid_time', 'evidence_note'])
def test_missing_property_fields_are_client_errors(tmp_path, field):
    body = property_command()
    del body[field]
    with pytest.raises(SceneLinkError, match='invalid_link_request'):
        SceneOntologyLinks(tmp_path, 'workspace', 'engineer', None).change(source(), body)


def test_property_noop_determinism_actor_and_object_isolation(tmp_path):
    service = SceneOntologyLinks(tmp_path, 'workspace', 'engineer', None)
    ref = publish_core(tmp_path)
    src = {**source(), 'objects': source()['objects'] + [{'object_id':'legacy.id:two','properties':{'name':'legacy name'}}]}
    service.change(src, command(ref))
    service.change(src, property_command())
    report = service.read(src)['instance_report']
    assert report['valid'] and report == service.read(src)['instance_report']
    assert not service.change(src, property_command(request_id='c'*32, expected_revision=2))['changed']
    assert report == service.read(src)['instance_report']
    link = service.read(src)['links'][0]
    assert link['properties_updated_by'] == 'engineer'
    assert link['instance_properties']['name']['value'] == 'manual name'
    service.change(src, command(ref, object_id='legacy.id:two', request_id='d'*32, expected_revision=2))
    report = service.read(src)['instance_report']
    assert not report['valid']
    assert [i['valid'] for i in report['objects']] == [True, False]
    assert 'instance_properties' not in service.read(src)['links'][1]
    # Invalid date prevents semantic checks on other entities too: fail closed.
    service.change(src, property_command(object_id='legacy.id:two', request_id='e'*32, expected_revision=3,
                                         valid_time={'start':'not-a-time', 'end':None}))
    report = service.read(src)['instance_report']
    assert not any(i['valid'] for i in report['objects'])
    assert any(i['code']=='object_validation_incomplete' for i in report['objects'][0]['diagnostics'])


def test_fixed_closure_version_conflict_is_explicit(tmp_path):
    service = SceneOntologyLinks(tmp_path, 'workspace', 'engineer', None)
    first = publish_core(tmp_path)
    second = publish_core(tmp_path, version='0.2.0', revision=1, base=first)
    src = {**source(), 'objects': source()['objects'] + [{'object_id':'two','properties':{}}]}
    service.change(src, command(first))
    service.change(src, command(second, object_id='two', request_id='b'*32, expected_revision=1))
    report = service.read(src)['instance_report']
    assert not report['valid'] and report['diagnostics'][0]['code']=='definition_version_conflict'
    assert report['diagnostics'][0]['state']=='conflict'


@pytest.mark.parametrize('claim,code', [
    ({'value':230,'unit':'V','quantity':'electric_potential'}, None),
    ({'value':True,'unit':'V','quantity':'electric_potential'}, 'schema_invalid'),
    ({'value':-1,'unit':'V','quantity':'electric_potential'}, 'property_below_minimum'),
    ({'value':230,'unit':'kV','quantity':'electric_potential'}, 'unit_mismatch'),
    ({'value':230,'unit':'V','quantity':'power'}, 'quantity_mismatch'),
])
def test_fixed_electrical_attributes_reach_independent_kernel(claim, code):
    from packages.service.scene_ontology_validation import validate_link_properties
    catalog = builtin_catalog()
    ref = next(item['reference'] for item in catalog.describe()['modules'] if item['reference']['module_id']=='electrical')
    link = {'object_id':'cabinet', 'reference':ref, 'concept_id':'distribution_cabinet',
            'linked_at':'2026-11-20T00:00:00Z', 'bundle':catalog.export('electrical'),
            'instance_properties':{'name':{'value':'test cabinet'}, 'rated_voltage':claim},
            'evidence_note':'synthetic test fixture'}
    report = validate_link_properties(source(), {'revision':1, 'links':[link]})
    assert report['valid'] is (code is None)
    if code:
        assert any(issue['code']==code for issue in report['diagnostics'])
