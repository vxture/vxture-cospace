"""Read candidate region membership and explicit annotated connection context."""
from typing import Annotated

from pydantic import Field

from packages.construction.ifc_review_snapshot import inspect_review_snapshot
from packages.spatial.ifc_annotations import Area
from packages.spatial.region_query import classify_region
from packages.spatial.scene_graph import Fixed, Identity, Vector
from packages.spatial.scene_identity import Digest, content_digest


class RegionQuery(Fixed):
    snapshot_sha256: Digest
    frame_id: Identity
    point_xyz_m: Vector
    boundary_tolerance_m: Annotated[float, Field(ge=0, le=1)]


def _connections(checked, area_ids):
    entities = {row['entity_id']: row for row in checked['structure']['entities']}
    complete = set(checked['annotation_check']['complete_annotation_ids'])
    rows, doors = [], []
    for connection in checked['snapshot']['annotations']['connections']:
        if not any(endpoint['area_id'] in area_ids for endpoint in connection['endpoints']):
            continue
        source = entities[connection['source_entity_id']]
        rows.append(connection | {'element_id': source['element_id'], 'source_role': source['source_role'],
                                  'annotation_status': 'complete' if source['entity_id'] in complete else 'partial',
                                  'assessment': 'unverified'})
        if source['source_role'] == 'door':
            doors.append(source['element_id'])
    return rows, doors


def query_review_regions(raw, *, query, design_package, expected_source, ontology_raw=None):
    """Caller authorizes fixed source and ontology; no navigation or implicit transform."""
    request = RegionQuery.model_validate(query)
    checked = inspect_review_snapshot(raw, expected_sha256=request.snapshot_sha256, design_package=design_package,
                                      expected_source=expected_source, ontology_raw=ontology_raw)
    if request.frame_id != checked['snapshot']['frame_id']:
        raise ValueError('region_query_frame_mismatch')
    areas = checked['snapshot']['annotations']['areas']
    matches = []
    for area in areas:
        result = classify_region(Area.model_validate(area), request.point_xyz_m, request.boundary_tolerance_m)
        if result is not None:
            matches.append({key: area[key] for key in ('id', 'name', 'level_id', 'evidence_ids')}
                           | result | {'assessment': 'unverified'})
    ids = {row['id'] for row in matches}
    connections, doors = _connections(checked, ids)
    value = {'profile': 'cospace.ifc-review-region-query/0.1', 'query': request.model_dump(),
             'source': checked['snapshot']['source'], 'result': 'matches' if matches else 'no_match',
             'annotation_coverage': 'provided_regions_only' if areas else 'no_regions_provided',
             'matches': matches, 'connections': connections, 'door_element_ids': doors,
             'door_observation_batch_supported': 1 <= len(doors) <= 128,
             'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
             'alignment_verified': False, 'ontology_bound': False, 'confirmed_connections': [],
             'real_release_ready': False,
             'limitations': ['single_ring_constant_height_regions', 'candidate_annotations_not_field_facts',
                             'no_match_not_proof_of_outside_building_or_free_space',
                             'all_overlapping_candidates_retained', 'boundary_band_extends_outside_region',
                             'connections_are_annotations_not_navigation', 'no_live_observations_included']}
    return value | {'cursor': content_digest(value)}
