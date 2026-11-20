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
    assert snapshot['instance_validation'] == 'not_performed'
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
