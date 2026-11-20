"""Translate explicit consumer claims to the portable instance validator.

No legacy property/type/relationship mapping is inferred. Geometry and service
publication are outside this partial validation profile.
"""
from hashlib import sha256

from packages.ontology.kernel import Catalog, canonical_bytes, validate_instances


def validate_link_properties(source, snapshot):
    links = sorted(snapshot['links'], key=lambda item: item['object_id'])
    result = {'scope': 'linked_object_attributes', 'revision': snapshot['revision'],
              'source_sha256': source['source_sha256'], 'valid': False,
              'relations_checked': False, 'geometry_checked': False,
              'professional_review': 'not_performed', 'diagnostics': [], 'objects': []}
    if not links:
        result['diagnostics'] = [{'code': 'no_linked_objects', 'path': '/links', 'state': 'not_recorded', 'severity': 'error'}]
        return result
    modules = {}
    for link in links:
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
        entity_id = 'object-' + sha256(link['object_id'].encode()).hexdigest()[:48]
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
    return result
