"""Bounded, deterministic instance validation. Standard library only; no storage.

The structural reader implements only the vocabulary of our packaged Schema.
It is not a general JSON Schema implementation or an assertion of site truth.
"""
from collections import defaultdict, deque
from datetime import datetime
from hashlib import sha256
import json
import math
import re

from .catalog import Catalog, canonical_bytes
from .instance_contract import instance_schema, park_baseline_rules

MAX_INSTANCE_BYTES = 4 * 1024 * 1024
MAX_DIAGNOSTICS = 200
MAX_WORK = 250000
SCHEMA_KEYWORDS = frozenset(('$schema', '$id', 'title', '$defs', '$ref', 'type', 'const', 'enum',
    'properties', 'required', 'additionalProperties', 'propertyNames', 'maxProperties',
    'dependentRequired', 'items', 'minItems', 'maxItems', 'uniqueItems', 'minLength', 'maxLength',
    'pattern', 'format', 'allOf', 'anyOf', 'oneOf', 'if', 'then'))


class _Stop(ValueError):
    def __init__(self, code, path='/'):
        self.code, self.path = code, path


def _pointer(path, key):
    return path.rstrip('/') + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _interval(record):
    period = record['valid_time']
    return _time(period['start']), _time(period['end']) if period['end'] else None


def _active(interval, point):
    return interval[0] <= point and (interval[1] is None or point < interval[1])


def _within(inner, outer):
    return inner[0] >= outer[0] and (outer[1] is None or inner[1] is not None and inner[1] <= outer[1])


class _Validation:
    def __init__(self):
        self.diagnostics = []
        self.seen = set()
        self.work = 0

    def tick(self, amount=1):
        self.work += amount
        if self.work > MAX_WORK:
            raise _Stop('work_budget')

    def add(self, code, path, severity='error', related=()):
        state = {'disputed_assertion': 'conflict', 'incomplete_coverage': 'unknown',
                 'geometry_not_recorded': 'not_recorded'}.get(code, 'unsatisfied')
        item = {'code': code, 'path': path or '/', 'severity': severity, 'state': state}
        if related:
            item['related_paths'] = sorted(set(related))
        key = canonical_bytes(item)
        if key not in self.seen:
            if len(self.diagnostics) >= MAX_DIAGNOSTICS:
                raise _Stop('diagnostic_budget')
            self.seen.add(key)
            self.diagnostics.append(item)

    def structure(self, value, schema, root, path=''):
        """Validate the packaged profile's closed subset, with calendar checking."""
        self.tick()
        if set(schema) - SCHEMA_KEYWORDS or schema.get('format') not in (None, 'date-time', 'uri'):
            raise _Stop('unsupported_schema', path or '/')
        if '$ref' in schema:
            if not schema['$ref'].startswith('#/$defs/'):
                raise _Stop('unsupported_schema', path or '/')
            return self.structure(value, root['$defs'][schema['$ref'].split('/')[-1]], root, path)
        if 'const' in schema and canonical_bytes(value) != canonical_bytes(schema['const']):
            self.add('schema_invalid', path)
        if 'enum' in schema and not any(canonical_bytes(value) == canonical_bytes(v) for v in schema['enum']):
            self.add('schema_invalid', path)
        types = schema.get('type', [])
        types = [types] if isinstance(types, str) else types
        actual = ('null' if value is None else 'boolean' if type(value) is bool else
                  'string' if type(value) is str else 'number' if type(value) in (int, float) else
                  'array' if type(value) is list else 'object')
        if types and actual not in types:
            self.add('schema_invalid', path)
            return
        if isinstance(value, dict):
            props = schema.get('properties', {})
            for key in schema.get('required', []):
                if key not in value:
                    self.add('schema_invalid', _pointer(path, key))
            if len(value) > schema.get('maxProperties', len(value)):
                self.add('schema_invalid', path)
            for key in sorted(value):
                child = _pointer(path, key)
                if 'propertyNames' in schema:
                    self.structure(key, schema['propertyNames'], root, child)
                if key in props:
                    self.structure(value[key], props[key], root, child)
                elif schema.get('additionalProperties') is False:
                    self.add('schema_invalid', child)
                elif isinstance(schema.get('additionalProperties'), dict):
                    self.structure(value[key], schema['additionalProperties'], root, child)
            for key, required in schema.get('dependentRequired', {}).items():
                if key in value:
                    for other in required:
                        if other not in value:
                            self.add('schema_invalid', _pointer(path, other))
        if isinstance(value, list):
            if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
                self.add('schema_invalid', path)
                return
            if schema.get('uniqueItems'):
                keys = set()
                for index, item in enumerate(value):
                    key = canonical_bytes(item)
                    if key in keys:
                        self.add('schema_invalid', _pointer(path, index))
                    keys.add(key)
            if 'items' in schema:
                for index, item in enumerate(value):
                    self.structure(item, schema['items'], root, _pointer(path, index))
        if isinstance(value, str):
            if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', len(value)):
                self.add('schema_invalid', path)
            if 'pattern' in schema and re.search(schema['pattern'], value) is None:
                self.add('schema_invalid', path)
            if schema.get('format') == 'date-time':
                try:
                    _time(value)
                except ValueError:
                    self.add('schema_invalid', path)
            if schema.get('format') == 'uri' and re.fullmatch(r'[a-z][a-z0-9+.-]*:[^\s]+', value) is None:
                self.add('schema_invalid', path)
        for sub in schema.get('allOf', []):
            self.structure(value, sub, root, path)
        for operator in ('anyOf', 'oneOf'):
            if operator in schema:
                matches = 0
                for sub in schema[operator]:
                    probe = _Validation()
                    probe.structure(value, sub, root, path)
                    self.tick(probe.work)
                    matches += not probe.diagnostics
                if not matches or operator == 'oneOf' and matches != 1:
                    self.add('schema_invalid', path)
        if 'if' in schema:
            probe = _Validation()
            probe.structure(value, schema['if'], root, path)
            self.tick(probe.work)
            if not probe.diagnostics and 'then' in schema:
                self.structure(value, schema['then'], root, path)

    def semantic(self, document, catalog, rules):
        supplied = {m['module_id']: m for m in catalog.export()['modules']}
        locked = {}
        for index, ref in enumerate(document['definition_refs']):
            path = f'/definition_refs/{index}'
            identity = ref['module_id']
            if identity in locked:
                self.add('duplicate_id', path + '/module_id')
            locked[identity] = ref
            module = supplied.get(identity)
            if module is None or module['version'] != ref['version']:
                self.add('definition_mismatch', path)
            elif sha256(canonical_bytes(module)).hexdigest() != ref['sha256']:
                self.add('definition_mismatch', path + '/sha256')
        for index, ref in enumerate(document['definition_refs']):
            module = supplied.get(ref['module_id'])
            if module and any(locked.get(r['module_id']) != r for r in module['requires']):
                self.add('dependency_mismatch', f'/definition_refs/{index}')
        if self.diagnostics:
            return
        modules = {key: supplied[key] for key in locked}
        concepts = {f'{m}:{k}': v for m, module in modules.items() for k, v in module['concepts'].items()}
        relations = {f'{m}:{k}': v for m, module in modules.items() for k, v in module['relations'].items()}
        ancestors, properties = {}, {}
        for identity in concepts:
            current, lineage, props = identity, set(), {}
            while current:
                self.tick()
                lineage.add(current)
                props.update(concepts[current]['properties'])
                current = concepts[current].get('parent')
            ancestors[identity], properties[identity] = lineage, props

        indexes = {}
        for collection in ('sources', 'evidence', 'entities', 'assertions', 'frames', 'geometries', 'coverage'):
            indexes[collection] = {}
            for index, item in enumerate(document[collection]):
                path = f'/{collection}/{index}'
                if item['id'] in indexes[collection]:
                    self.add('duplicate_id', path + '/id')
                indexes[collection][item['id']] = (item, path)
        if self.diagnostics:
            return
        entities = indexes['entities']
        periods = {}

        def references(record, path):
            if 'source_id' in record and record['source_id'] not in indexes['sources']:
                self.add('unresolved_source', path + '/source_id')
            for i, identity in enumerate(record.get('evidence_ids', [])):
                if identity not in indexes['evidence']:
                    self.add('unresolved_evidence', f'{path}/evidence_ids/{i}')
            if 'valid_time' in record:
                interval = _interval(record)
                if interval[1] is not None and interval[1] <= interval[0]:
                    self.add('invalid_interval', path + '/valid_time/end')
                else:
                    periods[path] = interval

        for evidence, path in indexes['evidence'].values():
            references(evidence, path)
        temporal = rules['temporal_concepts'] if rules else []
        for entity, path in entities.values():
            references(entity, path)
            concept = entity['type']
            if concept not in concepts:
                self.add('unresolved_concept', path + '/type')
                continue
            if any(t in ancestors[concept] for t in temporal) and 'valid_time' not in entity:
                self.add('required_valid_time', path + '/valid_time')
            for i, binding in enumerate(entity['source_bindings']):
                references(binding, f'{path}/source_bindings/{i}')
            declared = properties[concept]
            for key, definition in declared.items():
                if definition['required'] and key not in entity['properties']:
                    self.add('required_property', path + '/properties/' + key)
            for key, prop in entity['properties'].items():
                prop_path = path + '/properties/' + key
                references(prop, prop_path)
                if key not in declared:
                    self.add('unknown_property', prop_path)
                    continue
                definition, value = declared[key], prop['value']
                kind = definition['data_type']
                numeric = type(value) in (int, float)
                matches = {'string': type(value) is str, 'boolean': type(value) is bool,
                           'number': numeric, 'integer': numeric and value % 1 == 0}[kind]
                if not matches:
                    self.add('property_type_mismatch', prop_path + '/value')
                if type(value) is str and not value.strip():
                    self.add('empty_property', prop_path + '/value')
                if numeric and 'minimum' in definition and value < definition['minimum']:
                    self.add('property_below_minimum', prop_path + '/value')
                for field in ('unit', 'quantity'):
                    if prop.get(field) != definition.get(field):
                        self.add(field + '_mismatch', prop_path + '/' + field)
        edges = defaultdict(list)
        for assertion, path in indexes['assertions'].values():
            references(assertion, path)
            relation = relations.get(assertion['relation'])
            if relation is None:
                self.add('unresolved_relation', path + '/relation')
            for field, endpoint in (('subject_id', 'source_types'), ('object_id', 'target_types')):
                entity = entities.get(assertion[field])
                if entity is None:
                    self.add('unresolved_entity', path + '/' + field)
                elif relation and not ancestors.get(entity[0]['type'], set()).intersection(relation[endpoint]):
                    self.add('endpoint_type_mismatch', path + '/' + field)
            if assertion['epistemic_status'] == 'disputed':
                self.add('disputed_assertion', path, 'warning')
            elif relation and path in periods:
                edges[(assertion['subject_id'], assertion['relation'])].append((assertion, path, periods[path]))

        for geometry, path in indexes['geometries'].values():
            if geometry['frame_id'] not in indexes['frames']:
                self.add('unresolved_frame', path + '/frame_id')
            shape = geometry['shape']
            if shape['kind'] == 'box3' and any(a >= b for a, b in zip(shape['min'], shape['max'])):
                self.add('invalid_geometry', path + '/shape/min')
        for i, binding in enumerate(document['geometry_bindings']):
            path = f'/geometry_bindings/{i}'
            references(binding, path)
            entity = entities.get(binding['entity_id'])
            if entity is None:
                self.add('unresolved_entity', path + '/entity_id')
            else:
                lineage = ancestors.get(entity[0]['type'], set())
                if ('core:physical_object' not in lineage and 'core:spatial_region' not in lineage
                        or 'core:spatial_region' in lineage and binding['purpose'] != 'extent'):
                    self.add('geometry_binding_type_mismatch', path + '/purpose')
            if binding['geometry_id'] not in indexes['geometries']:
                self.add('unresolved_geometry', path + '/geometry_id')
        geometrically_bound = {b['entity_id'] for b in document['geometry_bindings']}
        for entity, path in entities.values():
            if (entity['id'] not in geometrically_bound and
                    ancestors.get(entity['type'], set()).intersection({'core:physical_object', 'core:spatial_region'})):
                self.add('geometry_not_recorded', path, 'info')
        for coverage, path in indexes['coverage'].values():
            references(coverage, path)
            for i, identity in enumerate(coverage['scope_entity_ids']):
                entity = entities.get(identity)
                if entity is None:
                    self.add('unresolved_entity', f'{path}/scope_entity_ids/{i}')
                elif 'core:spatial_region' not in ancestors.get(entity[0]['type'], set()):
                    self.add('endpoint_type_mismatch', f'{path}/scope_entity_ids/{i}')
            for field, registry in (('concepts', concepts), ('relations', relations)):
                for i, identity in enumerate(coverage[field]):
                    if identity not in registry:
                        self.add('unresolved_' + field[:-1], f'{path}/{field}/{i}')
            if coverage['status'] != 'complete':
                self.add('incomplete_coverage', path + '/status', 'info')
        # Do not derive global conclusions from dangling or ill-typed edges.
        if any(d['severity'] == 'error' for d in self.diagnostics) or rules is None:
            return
        for entity, path in entities.values():
            if any(t in ancestors[entity['type']] for t in temporal):
                for (subject, _), entries in edges.items():
                    self.tick()
                    if subject == entity['id']:
                        for _, edge_path, period in entries:
                            if not _within(period, periods[path]):
                                self.add('role_interval_outside', edge_path + '/valid_time')
            for rule in rules['cardinalities']:
                if rule['concept'] not in ancestors[entity['type']]:
                    continue
                entries = edges.get((entity['id'], rule['relation']), [])
                interval = periods.get(path)
                points = {t for _, _, p in entries for t in p if t is not None}
                if interval:
                    points.add(interval[0])
                    points = {p for p in points if _active(interval, p)}
                # Without an entity period, test the union of its asserted activity;
                # gaps have no inferred lifespan. Still require at least one edge.
                if not entries:
                    self.add('cardinality_violation', path)
                for point in sorted(points):
                    self.tick(len(entries) + 1)
                    active = {a['object_id'] for a, _, p in entries if _active(p, point)}
                    if not interval and not active:
                        continue
                    if len(active) < rule['minimum']:
                        self.add('role_interval_uncovered' if interval else 'cardinality_violation', path,
                                 related=[p + '/valid_time/end' for _, p, _ in entries])
                    elif rule['maximum'] is not None and len(active) > rule['maximum']:
                        self.add('cardinality_violation', path, related=[p for _, p, _ in entries])
        for hierarchy in rules['hierarchies']:
            self.hierarchy([entry for (_, relation), values in edges.items()
                            if relation == hierarchy['relation'] for entry in values], hierarchy)

    def hierarchy(self, entries, rule):
        points = sorted({t for _, _, period in entries for t in period if t is not None})
        for point in points:
            self.tick(len(entries) + 1)
            active = [(a, p) for a, p, interval in entries if _active(interval, point)]
            parents, paths, indegree = defaultdict(set), defaultdict(list), {}
            for edge, path in active:
                source, target = edge['subject_id'], edge['object_id']
                parents[source].add(target)
                paths[source].append(path)
                indegree.setdefault(source, 0)
                indegree.setdefault(target, 0)
            for source, targets in parents.items():
                if len(targets) > rule['maximum_parents']:
                    self.add('multiple_spatial_parents', paths[source][0], related=paths[source])
                for target in targets:
                    indegree[target] += 1
            if not rule['acyclic']:
                continue
            queue = deque(sorted(k for k, count in indegree.items() if not count))
            while queue:
                node = queue.popleft()
                self.tick()
                for target in sorted(parents.get(node, ())):
                    indegree[target] -= 1
                    if not indegree[target]:
                        queue.append(target)
            remaining = {node for node, count in indegree.items() if count}
            if remaining:
                related = [p + '/object_id' for a, p in active if a['subject_id'] in remaining and a['object_id'] in remaining]
                self.add('hierarchy_cycle', min(related), related=related)


def validate_instances(raw, catalog, *, rule_set=None):
    """Validate bytes against a supplied Catalog and optional park-baseline rules.

    Returns a deterministic report. No fetch, host identity, persistent state or
    truth inference. Unsupported/malformed input and exhausted budgets fail closed.
    Semantic validation never substitutes for authorization or field review.
    """
    validation = _Validation()
    document = None
    rules = park_baseline_rules() if rule_set == 'park-baseline' else None
    report = {'profile': 'vxture.ontology-instance-report/0.1', 'valid': False,
              'instance_sha256': None, 'library_sha256': None, 'rule_set': None,
              'schema_sha256': sha256(canonical_bytes(instance_schema())).hexdigest(),
              'diagnostics': []}
    if rules:
        report['rule_set'] = {key: rules[key] for key in ('rule_set_id', 'version')}
        report['rule_set']['sha256'] = sha256(canonical_bytes(rules)).hexdigest()
    try:
        if rule_set not in (None, 'park-baseline'):
            raise _Stop('unsupported_rule_set')
        if not isinstance(catalog, Catalog):
            raise _Stop('invalid_catalog')
        report['library_sha256'] = catalog.describe()['library_sha256']
        if type(raw) is not bytes:
            raise _Stop('invalid_input')
        if len(raw) > MAX_INSTANCE_BYTES:
            raise _Stop('size_budget')

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise _Stop('duplicate_key')
                result[key] = value
            return result

        def constant(_):
            raise _Stop('non_finite_number')

        document = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        # An iterative walk catches overflow floats and limits depth before recursion.
        pending = [(document, 0)]
        while pending:
            value, depth = pending.pop()
            validation.tick()
            if depth > 32:
                raise _Stop('depth_budget')
            if type(value) is float and not math.isfinite(value):
                raise _Stop('non_finite_number')
            if isinstance(value, (dict, list)):
                pending.extend((v, depth + 1) for v in (value.values() if isinstance(value, dict) else value))
        report['instance_sha256'] = sha256(canonical_bytes(document)).hexdigest()
        schema = instance_schema()
        validation.structure(document, schema, schema)
        if not validation.diagnostics:
            validation.semantic(document, catalog, rules)
    except _Stop as exc:
        # Budget errors always appear even if diagnostic capacity was exhausted.
        validation.diagnostics.append({'code': exc.code, 'path': exc.path, 'severity': 'error', 'state': 'unsatisfied'})
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        validation.diagnostics.append({'code': 'invalid_json', 'path': '/', 'severity': 'error', 'state': 'unsatisfied'})
    report['diagnostics'] = sorted(validation.diagnostics, key=lambda d: (d['path'], d['code'], d['severity']))
    report['valid'] = not any(d['severity'] == 'error' for d in report['diagnostics'])
    return report
