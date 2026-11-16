import pytest

from experiments.scripts.ifc_spatial_annotation import seed, validate_annotations


@pytest.fixture
def annotations():
    review = dict(frame_id='source-ifc', declared_levels=[{'global_id': 'level'}],
                  tasks=[dict(source_entity_id='door', source={'ifc_type': 'IfcDoor'}),
                         dict(source_entity_id='stair', source={'ifc_type': 'IfcStair'})])
    document = seed(review)
    document['evidence'] = [dict(id='drawing', sha256='a' * 64)]
    document['areas'] = [
        dict(id=key, name=key, level_id='level', z_range_m=[0, 3], evidence_ids=['drawing'],
             footprint_xy_m=[[x, 0], [x+2, 0], [x+2, 2], [x, 2]])
        for key, x in [('area-a', 0), ('area-b', 2)]]
    document['connections'][0].update(evidence_ids=['drawing'], endpoints=[
        dict(role='side_a', area_id='area-a', point_xyz_m=[1, 1, 0]),
        dict(role='side_b', area_id='area-b', point_xyz_m=[3, 1, 0])])
    return document, review


def test_empty_or_complete_annotations_remain_candidates(annotations):
    document, review = annotations
    assert validate_annotations(seed(review), review)['pending_annotation_ids'] == ['door', 'stair']
    result = validate_annotations(document, review)
    assert result['complete_annotation_ids'] == ['door']
    assert result['pending_annotation_ids'] == ['stair']
    assert result['confirmed_connections'] == []
    assert result['alignment_verified'] is result['evidence_content_verified'] is False
    document['connections'][0]['endpoints'].pop()
    assert validate_annotations(document, review)['complete_annotation_ids'] == []


@pytest.mark.parametrize('mutate,error', [
    (lambda d: d.update(frame_id='wrong'), 'source_binding'),
    (lambda d: d['areas'][0].update(level_id='missing'), 'level_reference'),
    (lambda d: d['areas'][0].update(evidence_ids=['missing']), 'evidence_reference'),
    (lambda d: d['areas'][0].update(footprint_xy_m=[[0, 0], [4, 4], [0, 3], [3, 0]]), 'area_geometry'),
    (lambda d: d['connections'].pop(), 'task_coverage'),
    (lambda d: d['connections'][0]['endpoints'][0].update(role='upper'), 'endpoint_roles'),
    (lambda d: d['connections'][0]['endpoints'][0].update(point_xyz_m=[1, 1, 4]), 'outside_area'),
    (lambda d: d['connections'][0]['endpoints'][0].update(point_xyz_m=[4, 4, 1]), 'outside_area'),
])
def test_inconsistent_annotations_rejected(annotations, mutate, error):
    document, review = annotations
    mutate(document)
    with pytest.raises(ValueError, match=error):
        validate_annotations(document, review)


def test_stair_lower_and_upper_follow_source_z(annotations):
    document, review = annotations
    document['connections'][1].update(evidence_ids=['drawing'], endpoints=[
        dict(role='lower', area_id='area-a', point_xyz_m=[1, 1, 2]),
        dict(role='upper', area_id='area-b', point_xyz_m=[3, 1, 1])])
    with pytest.raises(ValueError, match='stair_endpoint_order'):
        validate_annotations(document, review)
    document['connections'][1]['endpoints'][1]['point_xyz_m'][2] = 3
    assert validate_annotations(document, review)['complete_annotation_ids'] == ['door', 'stair']
