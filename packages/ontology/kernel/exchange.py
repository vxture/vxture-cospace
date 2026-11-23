"""Native definition closure exchange and a deliberately partial OWL projection."""
from hashlib import sha256
import json

from .catalog import Catalog, CatalogError, MAX_BYTES, MAX_MODULES, _reference, _require, _shape, canonical_bytes

PROFILE = 'vxture.ontology-exchange/0.1'
MAX_EXCHANGE_BYTES = MAX_BYTES + 4096


def _digest(document):
    return sha256(canonical_bytes(document)).hexdigest()


def _closure(bundle, module_id):
    try:
        catalog = Catalog.from_bytes(canonical_bytes(bundle))
        _require(catalog.export(module_id) == catalog.export(), 'unrelated_modules', '/modules')
    except CatalogError as exc:
        raise CatalogError(exc.code, '/bundle' + exc.path.rstrip('/')) from None
    except (TypeError, ValueError, RecursionError, OverflowError):
        raise CatalogError('invalid_json', '/bundle') from None
    return catalog


def export_closure(bundle, reference):
    """Return a transport package for exactly one target and its dependencies."""
    _reference(reference, '/reference')
    catalog = _closure(bundle, reference['module_id'])
    actual = next(entry['reference'] for entry in catalog.describe()['modules']
                  if entry['reference']['module_id'] == reference['module_id'])
    _require(actual == reference, 'reference_mismatch', '/reference')
    # Preserve the original module order as part of the published bundle digest.
    return {'profile': PROFILE, 'reference': dict(reference), 'bundle_sha256': _digest(bundle),
            'bundle': json.loads(canonical_bytes(bundle))}


def parse_closure(raw):
    """Verify UTF-8 JSON, exact digests and the complete closure; no host writes."""
    _require(type(raw) is bytes, 'invalid_json', '/')
    _require(len(raw) <= MAX_EXCHANGE_BYTES, 'size_budget', '/')

    def unique(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'duplicate_key', '/')
            result[key] = value
        return result

    def reject_constant(_):
        raise CatalogError('invalid_json', '/')

    try:
        document = json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=reject_constant)
    except CatalogError:
        raise
    except (ValueError, RecursionError):
        raise CatalogError('invalid_json', '/') from None
    _shape(document, ('profile', 'reference', 'bundle_sha256', 'bundle'), (), '/')
    _require(document['profile'] == PROFILE, 'unsupported_profile', '/profile')
    checked = export_closure(document['bundle'], document['reference'])
    _require(checked['bundle_sha256'] == document['bundle_sha256'], 'bundle_digest_mismatch', '/bundle_sha256')
    return checked


def catalog_from_exchanges(packages):
    """Assemble multiple roots for one instance package; reject mixed versions per module."""
    definitions = {}
    for index, raw in enumerate(packages):
        path = f'/exchanges/{index}'
        _require(index < MAX_MODULES, 'exchange_budget', '/exchanges')
        try:
            checked = parse_closure(raw)
        except CatalogError as exc:
            raise CatalogError(exc.code, path + exc.path.rstrip('/')) from None
        for offset, module in enumerate(checked['bundle']['modules']):
            identity, digest = module['module_id'], _digest(module)
            prior = definitions.get(identity)
            _require(prior is None or prior[0] == digest, 'exchange_dependency_conflict',
                     f'{path}/bundle/modules/{offset}')
            if prior is None:
                definitions[identity] = (digest, module)
                _require(len(definitions) <= MAX_MODULES, 'module_budget', '/exchanges')
    return Catalog([definitions[key][1] for key in sorted(definitions)])


def project_owl_classes(raw):
    """Map concepts and declared inheritance only; list native semantics omitted."""
    checked = parse_closure(raw)
    graph, omissions, terms = [], [], {}
    modules = checked['bundle']['modules']
    for module in modules:
        identity, version = module['module_id'], module['version']
        prefix = f'urn:vxture:ontology:concept:{identity}:{version}:{_digest(module)}:'
        terms.update({f'{identity}:{key}': prefix + key for key in module['concepts']})

    def omit(path, reason):
        omissions.append({'path': path, 'code': reason})

    for index, module in enumerate(modules):
        path = f'/bundle/modules/{index}'
        omit(path, 'module_metadata_and_dependency_contract_not_projected')
        for key, concept in sorted(module['concepts'].items()):
            concept_path = f'{path}/concepts/{key}'
            node = {'@id': terms[f'{module["module_id"]}:{key}'], '@type': 'owl:Class',
                    'rdfs:label': concept['title'], 'rdfs:comment': concept['definition']}
            if 'parent' in concept:
                node['rdfs:subClassOf'] = {'@id': terms[concept['parent']]}
            graph.append(node)
            for field in ('examples', 'counterexamples'):
                omit(f'{concept_path}/{field}', 'example_annotations_not_projected')
            for prop in sorted(concept['properties']):
                omit(f'{concept_path}/properties/{prop}', 'property_and_constraints_not_projected')
        for relation in sorted(module['relations']):
            omit(f'{path}/relations/{relation}', 'relation_and_constraints_not_projected')
    return {'profile': 'vxture.ontology-owl-class-projection/0.1', 'partial': True,
            'reference': checked['reference'], 'bundle_sha256': checked['bundle_sha256'],
            'omissions': omissions, 'document': {
                '@context': {'owl': 'http://www.w3.org/2002/07/owl#',
                             'rdfs': 'http://www.w3.org/2000/01/rdf-schema#'}, '@graph': graph}}
