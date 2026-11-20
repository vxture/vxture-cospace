from copy import deepcopy
import json
import pytest
from test_scene_ontology_relation_links import seeded, mapping
from test_scene_ontology_links import property_command
from packages.service.object_semantic_artifact import admit, preflight, freeze, MANIFEST


def prepare(tmp_path, mapped=False):
    service,source,ref=seeded(tmp_path)
    source.update(source_model_sha256='b'*64,frame_id='local',unit='m',axes=None)
    if mapped:service.change(source,mapping(ref))
    selection,report=preflight(service,source,dict(consumer_revision=5 if mapped else 4,
        source_manifest_sha256=source['source_sha256']))
    return service,source,selection,report


@pytest.mark.parametrize('mapped',[False,True])
def test_frozen_members_partial_coverage_identity_projection_and_stable_old_revision(tmp_path,mapped):
    service,source,selection,report=prepare(tmp_path,mapped)
    manifest,files=freeze(service,source,selection,'2026-11-20T10:00:00Z')
    assert manifest['assessment']['mapped_relation_validation']==('passed' if mapped else 'not_applicable')
    assert len(files)==5 and MANIFEST in files
    assert b'engineer' not in b''.join(files.values())
    assert 'workspace' != manifest['workspace_scope']
    claims=json.loads(files['claims.json'])
    assert claims['links'][0]['linked_by']==claims['links'][1]['linked_by']
    assert 'bundle' not in claims['links'][0] and 'definition' not in claims['links'][0]
    service.change(source,property_command(expected_revision=selection['consumer_revision'],
        request_id='f'*32,properties={'name':{'value':'new value'}}))
    after=preflight(service,source,{k:v for k,v in selection.items() if k!='snapshot_sha256'})[0]
    assert after==selection
    assert json.loads(files['claims.json'])==claims


def test_invalid_revision_source_digest_and_snapshot_do_not_fallback(tmp_path):
    service,source,selection,_=prepare(tmp_path)
    for changes in ({'consumer_revision':0},{'snapshot_sha256':'f'*64},{'source_manifest_sha256':'f'*64}):
        with pytest.raises(ValueError):freeze(service,source,selection|changes,'2026-11-20T10:00:00Z')
    with pytest.raises(ValueError,match='invalid_query_time'):
        freeze(service,source,selection,'2026-02-30T00:00:00Z')


def test_missing_evidence_invalid_properties_and_unknown_objects_block_adoption(tmp_path):
    service,source,selection,_=prepare(tmp_path)
    snapshot=service.fixed_snapshot(source,selection['consumer_revision'])
    for mutate in ('evidence','properties','object','duplicate'):
        bad=deepcopy(snapshot)
        if mutate=='evidence':bad['links'][0]['evidence_note']=' '
        if mutate=='properties':bad['links'][0]['instance_properties']={'name':{'value':12}}
        if mutate=='object':bad['links'][0]['object_id']='ghost'
        if mutate=='duplicate':bad['links'].append(deepcopy(bad['links'][0]))
        with pytest.raises(ValueError):admit(source,bad)


def test_relation_identity_and_direction_must_match_frozen_model(tmp_path):
    service,source,selection,_=prepare(tmp_path,True)
    snapshot=service.fixed_snapshot(source,selection['consumer_revision'])
    snapshot['relation_links'][0]['direction']='reverse'
    with pytest.raises(ValueError,match='semantic_relation_binding'):admit(source,snapshot)


def test_artifact_budget_is_not_silently_omitted(tmp_path,monkeypatch):
    service,source,selection,_=prepare(tmp_path)
    import packages.service.object_semantic_artifact as artifact
    monkeypatch.setattr(artifact,'MAX_BYTES',1)
    with pytest.raises(ValueError,match='semantic_size_budget'):
        freeze(service,source,selection,'2026-11-20T10:00:00Z')
