"""Translate explicit consumer claims to the portable instance validator.

No legacy property/type/relationship mapping is inferred. Geometry and service
publication are outside this partial validation profile.
"""
from hashlib import sha256

from packages.ontology.kernel import Catalog, canonical_bytes, validate_instances


def validate_link_properties(source, snapshot):
    return _validate_links(source, snapshot, False)


def validate_link_relations(source, snapshot):
    return _validate_links(source, snapshot, True)


def object_identity(value):
    return 'object-' + sha256(value.encode()).hexdigest()[:48]


def _validate_links(source, snapshot, include_relations):
    links = sorted(snapshot['links'], key=lambda item: item['object_id'])
    relations = sorted(snapshot.get('relation_links', []), key=lambda item: item['relation_id']) if include_relations else []
    result = {'scope': 'linked_attributes_and_mapped_relations' if include_relations else 'linked_object_attributes', 'revision': snapshot['revision'],
              'source_sha256': source['source_sha256'], 'valid': False,
              'relations_checked': include_relations, 'geometry_checked': False,
              'professional_review': 'not_performed', 'diagnostics': [], 'objects': []}
    if include_relations:
        result.update(relations=[], coverage='mapped_relations_only', unmapped_count=len(source.get('relations', [])) - len(relations))
    if not links:
        result['diagnostics'] = [{'code': 'no_linked_objects', 'path': '/links', 'state': 'not_recorded', 'severity': 'error'}]
        return result
    if include_relations:
        if not relations:
            result['diagnostics'] = [{'code': 'no_mapped_relations', 'path': '/relation_links', 'state': 'not_recorded', 'severity': 'error'}]
            return result
    modules = {}
    for link in links + relations:
        for module in link['bundle']['modules']:
            identity = module['module_id']
            if identity in modules and canonical_bytes(modules[identity]) != canonical_bytes(module):
                result['diagnostics'] = [{'code': 'definition_version_conflict', 'path': '/links',
                                          'state': 'conflict', 'severity': 'error', 'module_id': identity}]
                return result
            modules[identity] = module
    catalog = Catalog(list(modules.values()))
    generated = snapshot.get('updated_at') or max(link['linked_at'] for link in links)
    document = {'profile': 'vxture.ontology-instances/0.1', 'package_id': 'linked-object-attributes',
                'namespace': 'urn:cospace:scene:' + sha256(canonical_bytes([source['space_id'], source['candidate_id']])).hexdigest(),
                'synthetic': False, 'title': '空间对象人工实例声明', 'generated_at': generated,
                'definition_refs': [entry['reference'] for entry in catalog.describe()['modules']],
                'sources': [{'id': 'association-claims', 'system': 'cospace.spatial-association',
                             'scope': source['candidate_id'], 'revision': str(snapshot['revision']), 'synthetic': False}],
                'evidence': [], 'entities': [], 'assertions': [], 'frames': [],
                'geometries': [], 'geometry_bindings': [], 'coverage': []}
    for index, link in enumerate(links):
        evidence_id = 'claim-' + str(index)
        entity_id = object_identity(link['object_id'])
        document['evidence'].append({'id': evidence_id, 'source_id': 'association-claims',
            'record_key': link['object_id'], 'recorded_at': link.get('properties_updated_at', link['linked_at']),
            'description': link.get('evidence_note') or '对象类型引用声明；实例属性尚未人工维护，不表示现场核验。'})
        entity = {'id': entity_id, 'type': link['reference']['module_id'] + ':' + link['concept_id'],
                  'source_bindings': [{'source_id': 'association-claims', 'external_id': link['object_id']}],
                  'evidence_ids': [evidence_id], 'properties': {}}
        for key, prop in link.get('instance_properties', {}).items():
            entity['properties'][key] = {**prop, 'source_id': 'association-claims', 'evidence_ids': [evidence_id]}
        if link.get('instance_valid_time') is not None:
            entity['valid_time'] = link['instance_valid_time']
        document['entities'].append(entity)
    for index, link in enumerate(relations):
        evidence_id = 'relation-claim-' + str(index)
        document['evidence'].append({'id': evidence_id, 'source_id': 'association-claims',
            'record_key': link['relation_id'], 'recorded_at': link['linked_at'], 'description': link['evidence_note']})
        document['assertions'].append({'id': 'relation-' + sha256(link['relation_id'].encode()).hexdigest()[:48],
            'relation': link['reference']['module_id'] + ':' + link['definition_id'],
            'subject_id': object_identity(link['source_id']), 'object_id': object_identity(link['target_id']),
            'source_id': 'association-claims', 'evidence_ids': [evidence_id],
            'valid_time': link['valid_time'], 'epistemic_status': 'reported'})
    report = validate_instances(canonical_bytes(document), catalog)
    result.update(valid=report['valid'], diagnostics=report['diagnostics'],
                  instance_sha256=report['instance_sha256'], library_sha256=report['library_sha256'],
                  validator_profile=report['profile'])
    for index, link in enumerate(links):
        prefix = f'/entities/{index}'
        issues = [issue for issue in report['diagnostics'] if issue['path'] == prefix or issue['path'].startswith(prefix + '/')]
        global_errors = [issue for issue in report['diagnostics'] if issue['severity'] == 'error' and not issue['path'].startswith('/entities/')]
        # The kernel skips all semantic checks after a structural failure. Do
        # not mark other objects valid merely because they have no paths yet.
        structure_failed = any(issue['code'] == 'schema_invalid' for issue in report['diagnostics'])
        if structure_failed and not issues:
            issues = [{'code': 'object_validation_incomplete', 'path': prefix, 'severity': 'error', 'state': 'unknown'}]
        result['objects'].append({'object_id': link['object_id'],
                                  'valid': not any(issue['severity'] == 'error' for issue in issues) and not global_errors,
                                  'diagnostics': issues})
    if include_relations:
        # Relation validity is a set-level result. Entity, temporal or other
        # assertion failures can prevent or invalidate relation-set validation.
        for index, link in enumerate(relations):
            prefix = f'/assertions/{index}'
            issues = [issue for issue in report['diagnostics'] if issue['path'] == prefix or issue['path'].startswith(prefix + '/')]
            result['relations'].append({'relation_id': link['relation_id'], 'valid': report['valid'], 'diagnostics': issues})
    return result
