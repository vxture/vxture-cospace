"""Bounded, deterministic module validation and exact dependency resolution."""
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
import json
import math
import re

MODULE_PROFILE = 'vxture.ontology-module/0.1'
LIBRARY_PROFILE = 'vxture.ontology-library/0.1'
MAX_BYTES = 1024 * 1024
MAX_MODULES = 32
MAX_TERMS = 256
ID = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
VERSION = re.compile(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')


class CatalogError(ValueError):
    def __init__(self, code, path):
        self.code, self.path = code, path
        super().__init__(f'{code}: {path}')


def canonical_bytes(value):
    """Profile-local JSON encoding, not a claim of RFC 8785 canonicalization."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _require(condition, code, path):
    if not condition:
        raise CatalogError(code, path)


def _shape(value, required, optional, path):
    _require(type(value) is dict and set(required) <= value.keys()
             and value.keys() <= set(required) | set(optional), 'invalid_fields', path)


def _text(value, path, maximum=2000):
    _require(type(value) is str and bool(value.strip()) and len(value) <= maximum,
             'invalid_text', path)


def _identifier(value, path):
    _require(type(value) is str and ID.fullmatch(value) is not None, 'invalid_id', path)


def _reference(value, path):
    _shape(value, ('module_id', 'version', 'sha256'), (), path)
    _identifier(value['module_id'], path + '/module_id')
    _require(type(value['version']) is str and VERSION.fullmatch(value['version']) is not None,
             'invalid_version', path + '/version')
    _require(type(value['sha256']) is str and SHA.fullmatch(value['sha256']) is not None,
             'invalid_digest', path + '/sha256')


def _refs(value, path):
    _require(type(value) is list and 1 <= len(value) <= MAX_TERMS, 'invalid_endpoints', path)
    for index, item in enumerate(value):
        _text(item, f'{path}/{index}', 129)
    _require(len(set(value)) == len(value), 'duplicate_endpoint', path)


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _module(value, path):
    _shape(value, ('profile', 'module_id', 'version', 'title', 'description', 'layer',
                   'status', 'requires', 'concepts', 'relations'), (), path)
    _require(value['profile'] == MODULE_PROFILE, 'unsupported_profile', path + '/profile')
    _identifier(value['module_id'], path + '/module_id')
    _require(type(value['version']) is str and VERSION.fullmatch(value['version']) is not None,
             'invalid_version', path + '/version')
    _require(value['layer'] in ('core', 'domain'), 'invalid_layer', path + '/layer')
    # This first profile intentionally cannot assert that a definition is published.
    _require(value['status'] == 'draft', 'unsupported_status', path + '/status')
    _text(value['title'], path + '/title', 160)
    _text(value['description'], path + '/description')
    _require(type(value['requires']) is list and len(value['requires']) <= MAX_MODULES,
             'invalid_dependencies', path + '/requires')
    for index, reference in enumerate(value['requires']):
        _reference(reference, f'{path}/requires/{index}')
    _require(type(value['concepts']) is dict and 1 <= len(value['concepts']) <= MAX_TERMS,
             'invalid_concepts', path + '/concepts')
    _require(type(value['relations']) is dict and len(value['relations']) <= MAX_TERMS,
             'invalid_relations', path + '/relations')
    for identity, term in value['concepts'].items():
        term_path = f'{path}/concepts/{identity}'
        _identifier(identity, term_path)
        _shape(term, ('title', 'definition', 'examples', 'counterexamples', 'properties'), ('parent',), term_path)
        _text(term['title'], term_path + '/title', 160)
        _text(term['definition'], term_path + '/definition')
        if 'parent' in term:
            _text(term['parent'], term_path + '/parent', 129)
        for field in ('examples', 'counterexamples'):
            _require(type(term[field]) is list and 1 <= len(term[field]) <= 8,
                     'invalid_examples', term_path + '/' + field)
            for index, example in enumerate(term[field]):
                _text(example, f'{term_path}/{field}/{index}', 500)
        _require(type(term['properties']) is dict and len(term['properties']) <= 32,
                 'invalid_properties', term_path + '/properties')
        for key, prop in term['properties'].items():
            prop_path = f'{term_path}/properties/{key}'
            _identifier(key, prop_path)
            _shape(prop, ('title', 'definition', 'data_type', 'required'),
                   ('unit', 'quantity', 'minimum'), prop_path)
            _text(prop['title'], prop_path + '/title', 160)
            _text(prop['definition'], prop_path + '/definition')
            _require(prop['data_type'] in ('string', 'number', 'integer', 'boolean')
                     and type(prop['required']) is bool, 'invalid_property', prop_path)
            if 'unit' in prop or 'quantity' in prop:
                _require('unit' in prop and 'quantity' in prop and prop['data_type'] in ('number', 'integer'),
                         'invalid_unit', prop_path)
                _text(prop['unit'], prop_path + '/unit', 40)
                _text(prop['quantity'], prop_path + '/quantity', 80)
            if 'minimum' in prop:
                _require(prop['data_type'] in ('number', 'integer') and _finite_number(prop['minimum']),
                         'invalid_minimum', prop_path)
    for identity, relation in value['relations'].items():
        relation_path = f'{path}/relations/{identity}'
        _identifier(identity, relation_path)
        _shape(relation, ('title', 'definition', 'source_types', 'target_types', 'symmetric'), (), relation_path)
        _text(relation['title'], relation_path + '/title', 160)
        _text(relation['definition'], relation_path + '/definition')
        _refs(relation['source_types'], relation_path + '/source_types')
        _refs(relation['target_types'], relation_path + '/target_types')
        _require(type(relation['symmetric']) is bool, 'invalid_symmetry', relation_path)
        if relation['symmetric']:
            _require(set(relation['source_types']) == set(relation['target_types']),
                     'symmetric_endpoints_mismatch', relation_path)


class Catalog:
    """An immutable definition set; validation is not a statement of physical truth."""

    def __init__(self, modules):
        try:
            raw = canonical_bytes(modules)
        except (TypeError, ValueError, RecursionError, OverflowError) as exc:
            raise CatalogError('invalid_json', '/') from exc
        _require(len(raw) <= MAX_BYTES, 'size_budget', '/')
        _require(type(modules) is list and 1 <= len(modules) <= MAX_MODULES, 'module_budget', '/')
        self._modules = {}
        self._hashes = {}
        for index, original in enumerate(modules):
            path = f'/modules/{index}'
            _module(original, path)
            module = deepcopy(original)
            identity = module['module_id']
            _require(identity not in self._modules, 'duplicate_module', path)
            self._modules[identity] = module
            self._hashes[identity] = sha256(canonical_bytes(module)).hexdigest()
        for identity, module in self._modules.items():
            dependencies = set()
            for index, reference in enumerate(module['requires']):
                path = f'/modules/{identity}/requires/{index}'
                dependency = reference['module_id']
                _require(dependency not in dependencies, 'duplicate_dependency', path)
                dependencies.add(dependency)
                _require(dependency in self._modules, 'missing_dependency', path)
                self._check_reference(reference, path)
                _require(module['layer'] != 'core' or self._modules[dependency]['layer'] == 'core',
                         'core_depends_on_domain', path)
        for identity in sorted(self._modules):
            self._closure(identity, set(), set())
        self._concepts = {f'{identity}:{key}': term for identity, module in self._modules.items()
                          for key, term in module['concepts'].items()}
        for identity, module in self._modules.items():
            allowed = self._closure(identity, set(), set())
            def resolve(reference, path):
                _require(reference in self._concepts and reference.split(':')[0] in allowed,
                         'unresolved_concept', path)
            for key, term in module['concepts'].items():
                if 'parent' in term:
                    resolve(term['parent'], f'/modules/{identity}/concepts/{key}/parent')
            for key, relation in module['relations'].items():
                for field in ('source_types', 'target_types'):
                    for reference in relation[field]:
                        resolve(reference, f'/modules/{identity}/relations/{key}/{field}')
        for reference in self._concepts:
            seen = set()
            current = reference
            properties = set()
            while current:
                _require(current not in seen, 'inheritance_cycle', '/concepts/' + reference)
                seen.add(current)
                term = self._concepts[current]
                _require(not properties.intersection(term['properties']), 'property_override_unsupported', '/concepts/' + reference)
                properties.update(term['properties'])
                current = term.get('parent')

    @classmethod
    def from_bytes(cls, raw):
        _require(type(raw) is bytes and len(raw) <= MAX_BYTES, 'size_budget', '/')
        def pairs(items):
            result = {}
            for key, value in items:
                _require(key not in result, 'duplicate_key', '/')
                result[key] = value
            return result
        try:
            value = json.loads(raw, object_pairs_hook=pairs)
        except (ValueError, UnicodeError, RecursionError) as exc:
            if isinstance(exc, CatalogError):
                raise
            raise CatalogError('invalid_json', '/') from exc
        _shape(value, ('profile', 'modules'), (), '/')
        _require(value['profile'] == LIBRARY_PROFILE, 'unsupported_profile', '/profile')
        return cls(value['modules'])

    def _check_reference(self, reference, path):
        identity = reference['module_id']
        _require(reference['version'] == self._modules[identity]['version']
                 and reference['sha256'] == self._hashes[identity], 'dependency_mismatch', path)

    def _closure(self, identity, visiting, result):
        _require(identity not in visiting, 'dependency_cycle', '/modules/' + identity)
        if identity not in result:
            visiting.add(identity)
            for reference in self._modules[identity]['requires']:
                self._closure(reference['module_id'], visiting, result)
            visiting.remove(identity)
            result.add(identity)
        return result

    def export(self, module_id=None):
        """Export definitions with their transitive dependency closure."""
        _require(module_id is None or type(module_id) is str and module_id in self._modules,
                 'module_not_found', '/module_id')
        wanted = self._modules if module_id is None else self._closure(module_id, set(), set())
        return {'profile': LIBRARY_PROFILE,
                'modules': [deepcopy(self._modules[key]) for key in sorted(wanted)]}

    def describe(self):
        document = self.export()
        return {'profile': 'vxture.ontology-catalog/0.1', 'status': 'draft',
                'library_sha256': sha256(canonical_bytes(document)).hexdigest(),
                'capabilities': ['definition-validation', 'dependency-resolution', 'definition-export'],
                'modules': [{'reference': {'module_id': module['module_id'], 'version': module['version'],
                                           'sha256': self._hashes[module['module_id']]},
                             'definition': module} for module in document['modules']]}


def builtin_catalog():
    return Catalog.from_bytes(files(__package__).joinpath('definitions.json').read_bytes())
