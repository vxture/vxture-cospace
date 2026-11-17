from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from packages.service.ifc_review_regions import RegionQuery, query_review_regions
from packages.spatial.ifc_annotations import Area, _validate_area
from packages.spatial.region_query import classify_region
from packages.spatial.scene_identity import canonical, content_digest
from test_ifc_review_snapshot import review_env, structure_source, build, filled, sha


def area(poly=None):
    return Area.model_validate({'id': 'region', 'name': 'region', 'level_id': 'level',
        'footprint_xy_m': poly or [[0, 0], [2, 0], [2, 2], [0, 2]], 'z_range_m': [0, 3], 'evidence_ids': ['drawing']})


@pytest.mark.parametrize('point,tolerance,classification,distance', [
    ([1, 1, 1], 0, 'interior', 1), ([0, 1, 1], 0, 'boundary_candidate', 0),
    ([1, 1, 0], 0, 'boundary_candidate', 0), ([1, 1, 3], 0, 'boundary_candidate', 0),
    ([0, 0, 3], 0, 'boundary_candidate', 0), ([1, 1, 4], 0, None, None),
    ([-.1, 1, 1], .1, 'boundary_candidate', .1), ([.1, 1, 1], .1, 'boundary_candidate', .1),
    ([-.1, 1, -.1], .1, None, None),
    ([-.1, 1, -.1], .15, 'boundary_candidate', math.sqrt(.02)),
    ([1, 1, 3.2], .1, None, None), ([-1, 3, 1], 0, None, None),
])
def test_prism_classifies_inside_boundary_and_euclidean_outside_band(point, tolerance, classification, distance):
    result = classify_region(area(), point, tolerance)
    if classification is None:
        assert result is None
    else:
        assert result['classification'] == classification
        assert result['boundary_distance_m'] == pytest.approx(distance)


def test_concave_reversed_and_translated_polygons():
    poly = [[0, 0], [3, 0], [3, 1], [1, 1], [1, 3], [0, 3]]
    original = area(poly)
    _validate_area(original)
    assert classify_region(original, [2, 2, 1], 0) is None
    expected = classify_region(original, [.5, 2, 1], .01)
    reversed_area = area(list(reversed(poly)))
    assert classify_region(reversed_area, [.5, 2, 1], .01) == expected
    translated = area([[x + 100, y - 50] for x, y in poly])
    assert classify_region(translated, [100.5, -48, 1], .01) == expected


def query(result, **kwargs):
    doc = json.loads(result['snapshot'])
    request = {'snapshot_sha256': sha(result['snapshot']), 'frame_id': doc['frame_id'],
               'point_xyz_m': [1, 1, 1], 'boundary_tolerance_m': .01} | kwargs
    return query_review_regions(result['snapshot'], query=request, design_package=result['design_package'],
                                 expected_source=doc['source'])


def test_query_preserves_connection_context_and_observation_handoff_ids(review_env):
    result = build(review_env, worksheet=filled(review_env[2]))
    before = deepcopy(result)
    response = query(result)
    assert response['result'] == 'matches'
    assert [row['id'] for row in response['matches']] == ['area-a']
    assert response['matches'][0]['classification'] == 'interior'
    connection = response['connections'][0]
    assert connection['source_entity_id'] == 'door'
    assert connection['annotation_status'] == 'complete'
    assert [point['area_id'] for point in connection['endpoints']] == ['area-a', 'area-b']
    assert response['door_element_ids'] == ['e00002']
    assert response['door_observation_batch_supported'] is True
    assert response['cursor'] == content_digest({k: v for k, v in response.items() if k != 'cursor'})
    assert response['confirmed_connections'] == []
    assert response['real_release_ready'] is False
    assert 'states' not in response
    assert result == before


def test_shared_boundary_and_overlapping_regions_keep_every_candidate(review_env):
    sheet = filled(review_env[2])
    result = build(review_env, worksheet=sheet)
    response = query(result, point_xyz_m=[2, 1, 1])
    assert [row['id'] for row in response['matches']] == ['area-a', 'area-b']
    assert all(row['classification'] == 'boundary_candidate' for row in response['matches'])
    assert len(response['connections']) == 1
    sheet['areas'].append(sheet['areas'][0] | {'id': 'overlapping'})
    overlap = query(build(review_env, worksheet=sheet))
    assert [row['id'] for row in overlap['matches']] == ['area-a', 'overlapping']


def test_uncovered_and_empty_are_distinct_from_corruption(review_env):
    empty = query(build(review_env))
    assert empty['result'] == 'no_match'
    assert empty['annotation_coverage'] == 'no_regions_provided'
    assert empty['door_element_ids'] == []
    assert empty['door_observation_batch_supported'] is False
    result = build(review_env, worksheet=filled(review_env[2]))
    outside = query(result, point_xyz_m=[50, 50, 50])
    assert outside['result'] == 'no_match'
    assert outside['annotation_coverage'] == 'provided_regions_only'
    result['design_package'] += b'corrupt'
    with pytest.raises(ValueError, match='byte_digest'):
        query(result)


def test_partial_connection_stays_partial_and_does_not_invent_other_endpoint(review_env):
    sheet = filled(review_env[2])
    sheet['connections'][0]['endpoints'].pop()
    response = query(build(review_env, worksheet=sheet))
    assert response['connections'][0]['annotation_status'] == 'partial'
    assert len(response['connections'][0]['endpoints']) == 1


def test_region_handoff_uses_same_snapshot_for_reported_state(review_env, tmp_path):
    from types import SimpleNamespace
    from packages.infrastructure.spatial_observation_store import ObservationJournal
    from packages.service.ifc_opening_observations import observation_scope
    from packages.service.ifc_review_observations import read_review_observations
    from test_observation_journal import report
    result = build(review_env, worksheet=filled(review_env[2]))
    regions = query(result)
    principal = SimpleNamespace(issuer='https://example.invalid', org_id='test-org', workspace_id='test-workspace')
    source = regions['source']
    scope = observation_scope(principal, source['space_id'], source['catalog_sha256'])
    journal = ObservationJournal(tmp_path / 'observations', clock=lambda: '2026-11-17T00:01:00Z')
    journal.register({'profile': 'cospace.opening-observation-registration/0.1', 'scope': scope,
        'data_kind': 'ifc_design_candidate', 'subjects': [{'entity_id': 'door', 'role': 'door'}], 'producers': ['sensor-a']})
    journal.append(scope, report(entity_id='door', value='closed'), authenticated_producer='sensor-a')
    request = {'snapshot_sha256': regions['query']['snapshot_sha256'], 'element_ids': regions['door_element_ids']}
    before = journal.path.read_bytes()
    observed = read_review_observations(journal, principal, result['snapshot'], query=request,
        design_package=result['design_package'], expected_source=source, now='2026-11-17T00:05:00Z')
    assert observed['states'][0]['value'] == 'closed'
    assert observed['snapshot_sha256'] == regions['query']['snapshot_sha256']
    assert len(query(result)['connections']) == 1
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize('change', [
    {'frame_id': 'wrong-frame'}, {'point_xyz_m': [1, 2]}, {'point_xyz_m': [float('nan'), 0, 0]},
    {'boundary_tolerance_m': -1}, {'boundary_tolerance_m': 2}, {'point_xyz_m': [1e8, 0, 0]},
    {'snapshot_sha256': 'a' * 64}, {'extra': 'unexpected'},
])
def test_bad_query_fails_instead_of_no_match(review_env, change):
    result = build(review_env)
    with pytest.raises(ValueError):
        query(result, **change)


def test_query_cursor_changes_with_tolerance_point_and_annotation_revision(review_env):
    result = build(review_env, worksheet=filled(review_env[2]))
    response = query(result)
    assert query(result) == response
    assert query(result, boundary_tolerance_m=.02)['cursor'] != response['cursor']
    assert query(result, point_xyz_m=[1, 1, 1.1])['cursor'] != response['cursor']
    sheet = filled(review_env[2])
    sheet['areas'][0]['name'] = 'renamed candidate'
    assert query(build(review_env, worksheet=sheet))['cursor'] != response['cursor']


def test_cli_exclusive_output_and_schema(review_env, tmp_path, monkeypatch):
    from experiments.scripts.ifc_review_regions import main
    result = build(review_env, worksheet=filled(review_env[2]))
    doc = json.loads(result['snapshot'])
    request = {'snapshot_sha256': sha(result['snapshot']), 'frame_id': doc['frame_id'],
               'point_xyz_m': [1, 1, 1], 'boundary_tolerance_m': .01}
    for name, raw in [('snapshot.json', result['snapshot']), ('design.bin', result['design_package']),
                      ('source.json', canonical(doc['source'])), ('query.json', canonical(request))]:
        (tmp_path / name).write_bytes(raw)
    output = tmp_path / 'response.json'
    monkeypatch.setattr('sys.argv', ['ifc_review_regions', '--snapshot', str(tmp_path / 'snapshot.json'),
        '--design-package', str(tmp_path / 'design.bin'), '--source', str(tmp_path / 'source.json'),
        '--query', str(tmp_path / 'query.json'), '--output', str(output)])
    main()
    assert json.loads(output.read_bytes()) == query(result)
    with pytest.raises(FileExistsError):
        main()
    schema = json.loads(Path('contracts/schemas/ifc-review-region-query-v0.1.schema.json').read_bytes())
    assert schema == RegionQuery.model_json_schema()
