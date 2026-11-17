"""Describe actionable review-input gaps without asserting field or release readiness."""
from packages.construction.ifc_review_snapshot import inspect_review_snapshot
from packages.data.evidence_content import check_evidence_content
from packages.spatial.scene_identity import content_digest


def _connection_tasks(checked):
    entities = {row['entity_id']: row for row in checked['structure']['entities']}
    complete = set(checked['annotation_check']['complete_annotation_ids'])
    tasks = []
    for row in checked['snapshot']['annotations']['connections']:
        source = entities[row['source_entity_id']]
        required = ['side_a', 'side_b'] if source['ifc_type'] == 'IfcDoor' else ['lower', 'upper']
        supplied = {end['role'] for end in row['endpoints']}
        tasks.append({'source_entity_id': source['entity_id'], 'element_id': source['element_id'],
                      'ifc_type': source['ifc_type'],
                      'missing_endpoint_roles': [role for role in required if role not in supplied],
                      'evidence_reference_missing': not row['evidence_ids'],
                      'annotation_complete': source['entity_id'] in complete,
                      'assessment': 'unverified'})
    return sorted(tasks, key=lambda task: task['source_entity_id'])


def _semantics(checked):
    proposal = checked['type_proposals']
    if proposal is None:
        return {'status': 'mapping_not_supplied', 'proposed_count': 0,
                'unmapped_source_entity_ids': sorted(row['entity_id'] for row in checked['structure']['entities']),
                'ontology_bound': False}
    return {'status': 'proposals_only', 'proposed_count': proposal['proposed_count'],
            'unmapped_source_entity_ids': sorted(row['source_entity_id'] for row in proposal['entities']
                                               if row['status'] == 'unmapped'),
            'ontology_bound': False}


def _evidence(layer, pin, root):
    references = layer['evidence']
    used = {identity for row in layer['areas'] + layer['connections'] for identity in row['evidence_ids']}
    receipt = None
    if root is not None and references:
        try:
            receipt = check_evidence_content(root, references, document_sha256=pin)
        except OSError:
            raise ValueError('review_evidence_unavailable') from None
    return {'status': 'no_references' if not references else ('bytes_checked' if receipt else 'references_only'),
            'reference_count': len(references),
            'used_evidence_ids': sorted(used),
            'unused_evidence_ids': sorted(row['id'] for row in references if row['id'] not in used),
            'receipt': receipt, 'meaning_verified': False}


def assess_review_gaps(raw, *, expected_sha256, design_package, expected_source,
                       ontology_raw=None, evidence_root=None):
    """Authorize source/root externally. Fully validate fixed inputs before diagnosing gaps.

    No approval flags or vendor claims are accepted. A populated annotation is
    syntactically complete, not a confirmed physical connection or adopted fact.
    """
    checked = inspect_review_snapshot(raw, expected_sha256=expected_sha256, design_package=design_package,
                                      expected_source=expected_source, ontology_raw=ontology_raw)
    snapshot = checked['snapshot']
    layer = snapshot['annotations']
    tasks = _connection_tasks(checked)
    complete = sum(task['annotation_complete'] for task in tasks)
    linked = {end['area_id'] for row in layer['connections'] for end in row['endpoints']}
    value = {'profile': 'cospace.ifc-review-gaps/0.1',
             'snapshot_sha256': expected_sha256, 'source': snapshot['source'],
             'design_package_sha256': snapshot['design_package_sha256'],
             'structure_sha256': snapshot['structure_sha256'], 'frame_id': snapshot['frame_id'],
             'sg3': {'regions': {'status': 'provided_regions_only' if layer['areas'] else 'no_regions_provided',
                                'count': len(layer['areas']),
                                'without_connection_endpoint_ids': sorted(row['id'] for row in layer['areas']
                                                                          if row['id'] not in linked)},
                     'connections': {'total': len(tasks), 'complete_annotations': complete,
                                     'pending_annotations': len(tasks) - complete, 'tasks': tasks},
                     'evidence': _evidence(layer, expected_sha256, evidence_root),
                     'not_established_by_snapshot': ['point_cloud_units_and_alignment', 'field_region_coverage',
                                                     'field_connections', 'asset_identity']},
             'sg4': {'semantics': _semantics(checked),
                     'not_established_by_snapshot': ['fact_adoption', 'authorized_release',
                                                     'production_performance_and_failure_acceptance']},
             'sg5': {'status': 'observations_not_assessed',
                     'source_declared_door_element_ids': sorted(row['element_id'] for row in checked['structure']['entities']
                                                               if row['ifc_type'] == 'IfcDoor'),
                     'not_established_by_snapshot': ['manufacturer_identity', 'source_clock_and_evidence',
                                                     'real_reports', 'real_change_and_local_update_acceptance']},
             'data_kind': 'ifc_design_candidate', 'assessment': 'unverified', 'real_release_ready': False,
             'limitations': ['input_gaps_not_release_approval', 'annotation_completeness_not_field_truth',
                             'unlinked_regions_not_proof_of_disconnection', 'unmapped_entities_not_mandatory_types',
                             'no_observation_log_read_or_navigation_decision']}
    return value | {'report_sha256': content_digest(value)}
