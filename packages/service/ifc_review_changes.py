"""Compare review descriptions on one fixed design source; no rebuild or adoption."""
from packages.construction.ifc_review_snapshot import inspect_review_snapshot


def _difference(before, after, key):
    a, b = {row[key]: row for row in before}, {row[key]: row for row in after}
    return {'added': sorted(b.keys() - a.keys()), 'removed': sorted(a.keys() - b.keys()),
            'revised': sorted(identity for identity in a.keys() & b.keys() if a[identity] != b[identity])}


def _changed(delta):
    return set(delta['added'] + delta['removed'] + delta['revised'])


def _type_rows(value):
    proposal = value['type_proposals']
    return ([] if proposal is None else [{'entity_id': row['source_entity_id'], 'target_type_id': row['target_type_id']}
                                        for row in proposal['entities'] if row['target_type_id'] is not None])


def _annotation_impact(a, b, sections):
    affected_areas = _changed(sections['areas'])
    changed_evidence = _changed(sections['evidence'])
    for area in a['areas'] + b['areas']:
        if changed_evidence.intersection(area['evidence_ids']):
            affected_areas.add(area['id'])
    affected_connections = _changed(sections['connections'])
    for connection in a['connections'] + b['connections']:
        if (changed_evidence.intersection(connection['evidence_ids'])
                or any(endpoint['area_id'] in affected_areas for endpoint in connection['endpoints'])):
            affected_connections.add(connection['source_entity_id'])
    return affected_areas, affected_connections, changed_evidence


def compare_review_snapshots(base_raw, target_raw, *, base_sha256, target_sha256, design_package,
                             expected_source, base_ontology=None, target_ontology=None):
    """Both snapshots must reference the same exact design package and source.

    Annotation local IDs stay in their own namespace, separate from IFC IDs.
    """
    base = inspect_review_snapshot(base_raw, expected_sha256=base_sha256, design_package=design_package,
                                   expected_source=expected_source, ontology_raw=base_ontology)
    target = inspect_review_snapshot(target_raw, expected_sha256=target_sha256, design_package=design_package,
                                     expected_source=expected_source, ontology_raw=target_ontology)
    a, b = base['snapshot']['annotations'], target['snapshot']['annotations']
    sections = {key: _difference(a[key], b[key], 'source_entity_id' if key == 'connections' else 'id')
                for key in ('areas', 'connections', 'evidence')}
    sections['types'] = _difference(_type_rows(base), _type_rows(target), 'entity_id')
    old_mapping, new_mapping = base['snapshot']['mapping'], target['snapshot']['mapping']
    ontology_changed = ((old_mapping['ontology_ref'] if old_mapping else None)
                        != (new_mapping['ontology_ref'] if new_mapping else None))
    affected_areas, affected_connections, changed_evidence = _annotation_impact(a, b, sections)
    affected_source = _changed(sections['types'])
    if ontology_changed:
        affected_source.update(row['entity_id'] for row in _type_rows(base) + _type_rows(target))
    affected_source.update(affected_connections)
    components = []
    if affected_areas:
        components.append('spatial_regions')
    if affected_connections:
        components.append('structural_connections')
    if _changed(sections['types']) or ontology_changed:
        components.append('semantic_types')
    elif old_mapping != new_mapping:
        components.append('semantic_mapping_review')
    if changed_evidence:
        components.append('evidence_review')
    provenance_changed = any(a[key] != b[key] for key in ('original_worksheet_sha256', 'original_review_sha256'))
    return {'profile': 'cospace.ifc-review-changes/0.1', 'base_sha256': base_sha256, 'target_sha256': target_sha256,
            'source': expected_source, 'sections': sections, 'ontology_context_changed': ontology_changed,
            'mapping_changed': old_mapping != new_mapping,
            'provenance_changed': provenance_changed, 'affected_area_ids': sorted(affected_areas),
            'affected_source_entity_ids': sorted(affected_source), 'review_components': components,
            'design_geometry_changed': False, 'observation_changes_included': False,
            'review_required': bool(components) or provenance_changed,
            'assessment': 'unverified', 'real_release_ready': False,
            'limitations': ['description_changes_not_field_changes', 'same_fixed_design_source_only',
                            'annotation_ids_not_global_entity_ids', 'no_automatic_rebuild_or_adoption',
                            'observations_remain_a_separate_time_context']}
