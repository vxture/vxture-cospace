"""Small vocabulary constraints, not a general ontology engine."""


def validate_instances(ontology, objects):
    definitions = ontology['types']
    if not isinstance(definitions, dict) or not definitions:
        raise ValueError('ontology.types must be a nonempty object')
    seen = set()
    for obj in objects:
        identity = obj['object_id']
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError('object_id must be nonempty and unique')
        seen.add(identity)
        definition = definitions.get(obj['type_id'])
        if definition is None:
            raise ValueError(f'unknown ontology type: {obj["type_id"]} on {identity} /type_id')
        if obj['confirmation'] != 'synthetic':
            raise ValueError('sample objects must declare synthetic confirmation')
        properties = obj['properties']
        allowed = definition['properties']
        if set(properties) - set(allowed):
            raise ValueError(f'undefined properties on {identity} /properties')
        for name, rule in allowed.items():
            if rule['type'] != 'string':
                raise ValueError('sample ontology only supports string properties')
            if rule['required'] and name not in properties:
                raise ValueError(f'missing property {name} on {identity} /properties/{name}')
            if name in properties and not isinstance(properties[name], str):
                raise ValueError(f'invalid property type {name} on {identity} /properties/{name}')


def inspect_instances(ontology, objects):
    """Recompute using the fixed rule package, never a cached pass label."""
    from copy import deepcopy
    validate_instances(ontology, objects)
    return {'representation': 'ontology_inspection_v0.1', 'definition': deepcopy(ontology),
            'validation': {'status': 'passed', 'method': 'synthetic_string_rules_v0.1',
                           'scope': 'type membership, declared string properties and required presence',
                           'object_count': len(objects)},
            'objects': [{**deepcopy(obj), 'validation': 'passed', 'evidence_ids': None,
                         'evidence_status': 'object_links_not_recorded'} for obj in objects]}
