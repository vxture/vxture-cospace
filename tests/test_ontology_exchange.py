from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from packages.ontology.kernel import CatalogError, builtin_catalog, canonical_bytes, validate_instances
from packages.ontology.kernel.authoring import AuthoringError
from packages.ontology.kernel.exchange import (
    MAX_EXCHANGE_BYTES, catalog_from_exchanges, export_closure, parse_closure, project_owl_classes,
)
from packages.ontology.kernel.workbench import DefinitionWorkbench


class Port:
    def __init__(self):
        self.state = {}

    @contextmanager
    def transaction(self, scope):
        state = deepcopy(self.state.get(scope, {}))
        yield state
        if state:
            self.state[scope] = state


def module_ref(module):
    return {'module_id': module['module_id'], 'version': module['version'],
            'sha256': sha256(canonical_bytes(module)).hexdigest()}


def package(bundle, module_id):
    module = next(m for m in bundle['modules'] if m['module_id'] == module_id)
    return canonical_bytes(export_closure(bundle, module_ref(module)))


def author(port, scope, actor='writer'):
    roles = {'writer': {'read', 'read_private', 'edit', 'submit'}, 'reviewer': {'review'},
             'publisher': {'publish'}, 'reader': {'read'}}
    return DefinitionWorkbench(port, scope, actor, authorize=lambda s, a, action: s == scope and action in roles[a])


def stage(workbench, raw, revision, marker):
    return workbench.import_draft(raw, request_id=f'{marker:032x}', expected_revision=revision)


def publish(port, scope, module, revision, marker):
    pending = author(port, scope).change(dict(action='submit', module_id=module, expected_revision=revision,
                                             request_id=f'{marker:032x}'))
    review_id = pending['review_id']
    author(port, scope, 'reviewer').change(dict(action='decide', decision='approved', reason='Synthetic fixture',
                                                request_id=f'{marker + 1:032x}', review_id=review_id))
    return author(port, scope, 'publisher').change(dict(action='publish', expected_revision=revision,
                                                        request_id=f'{marker + 2:032x}', review_id=review_id))


def test_exchange_roundtrip_preserves_historical_dependencies_and_requires_local_approval():
    port = Port()
    source, dest = (author(port, scope) for scope in ('source', 'dest'))
    catalog = builtin_catalog()
    core = catalog.export('core')
    electrical = catalog.export('electrical')
    electrical['modules'].reverse()  # preserve original frozen bundle byte order, not just per-module digests
    stage(source, package(core, 'core'), 0, 1)
    base = publish(port, 'source', 'core', 1, 2)
    stage(source, package(electrical, 'electrical'), 0, 5)
    frozen = publish(port, 'source', 'electrical', 1, 6)
    core['modules'][0]['version'] = '0.2.0'
    assert stage(source, package(core, 'core'), 1, 9)['base_reference'] == base['reference']
    publish(port, 'source', 'core', 2, 10)

    raw = canonical_bytes(author(port, 'source', 'reader').export_release(frozen['reference']))
    checked = parse_closure(raw)
    assert checked['bundle_sha256'] == frozen['bundle_sha256']
    assert checked['bundle'] == electrical and checked['reference'] == frozen['reference']
    assert 'review' not in checked and 'published_at' not in checked
    assert canonical_bytes(checked) == raw
    with pytest.raises(AuthoringError, match='release_not_found'):
        dest.export_release(frozen['reference'])  # built-in candidate with the same bytes is not a release
    with pytest.raises(AuthoringError, match='forbidden'):
        author(port, 'dest', 'reader').preflight_import(raw)

    before = deepcopy(port.state)
    plan = dest.preflight_import(raw)
    assert port.state == before
    assert plan['can_import'] and plan['expected_revision'] == 0
    assert plan['dependencies'] == [{'reference': base['reference'], 'state': 'unpublished'}]
    staged = stage(dest, raw, 0, 13)
    assert staged['sha256'] == frozen['bundle_sha256']
    assert stage(dest, raw, 0, 13) == staged  # transport retry returns the original draft revision
    assert dest.preflight_import(raw)['diagnostics'][0]['code'] == 'exchange_already_draft'
    assert not dest.read('electrical')['releases']
    with pytest.raises(AuthoringError, match='release_not_found'):
        publish(port, 'dest', 'electrical', 1, 14)

    stage(dest, canonical_bytes(source.export_release(base['reference'])), 0, 17)
    publish(port, 'dest', 'core', 1, 18)
    assert dest.preflight_import(raw)['dependencies'][0]['state'] == 'published'
    local = publish(port, 'dest', 'electrical', 1, 21)
    assert local['reference'] == frozen['reference']
    assert canonical_bytes(dest.export_release(local['reference'])) == raw
    assert dest.preflight_import(raw)['diagnostics'][0]['code'] == 'exchange_already_published'


def test_import_rechecks_conflicts_and_revisions_after_preflight():
    port = Port()
    dest = author(port, 'dest')
    catalog = builtin_catalog()
    raw = package(catalog.export('electrical'), 'electrical')
    assert dest.preflight_import(raw)['can_import']
    wrong_core = catalog.export('core')
    wrong_core['modules'][0]['title'] = '另一套核心定义'
    stage(dest, package(wrong_core, 'core'), 0, 1)
    assert not dest.preflight_import(raw)['can_import']  # a conflicting dependency draft is also surfaced
    publish(port, 'dest', 'core', 1, 2)
    diagnostics = dest.preflight_import(raw)['diagnostics']
    assert diagnostics == [{'code': 'exchange_version_conflict', 'path': '/bundle/modules/0'}]
    before = deepcopy(port.state)
    with pytest.raises(AuthoringError, match='exchange_version_conflict'):
        stage(dest, raw, 0, 5)
    assert port.state == before
    raw_outdoor = package(catalog.export('outdoor'), 'outdoor')
    assert author(port, 'other').preflight_import(raw_outdoor)['can_import']
    other = author(port, 'other')
    stage(other, raw_outdoor, 0, 6)
    with pytest.raises(AuthoringError, match='revision_changed'):
        stage(other, raw_outdoor, 0, 7)
    changed = catalog.export('outdoor')
    next(m for m in changed['modules'] if m['module_id'] == 'outdoor')['title'] = '另一套室外定义'
    assert other.preflight_import(package(changed, 'outdoor'))['diagnostics'][0]['code'] == 'exchange_version_conflict'


def test_exchange_fails_closed_on_tamper_incomplete_closure_and_claimed_status():
    catalog = builtin_catalog()
    original = parse_closure(package(catalog.export('electrical'), 'electrical'))
    for code, attack in (
        ('bundle_digest_mismatch', lambda data: data.update(bundle_sha256='0' * 64)),
        ('reference_mismatch', lambda data: data['reference'].update(sha256='0' * 64)),
        ('missing_dependency', lambda data: data['bundle']['modules'].pop(0)),
        ('unsupported_status', lambda data: data['bundle']['modules'][0].update(status='published')),
        ('invalid_fields', lambda data: data.update(published_by='external-reviewer')),
        ('unrelated_modules', lambda data: data['bundle']['modules'].append(catalog.export('outdoor')['modules'][-1])),
    ):
        document = deepcopy(original)
        attack(document)
        with pytest.raises(CatalogError, match=code):
            parse_closure(canonical_bytes(document))
    for bad, code in ((b'{"profile":1,"profile":2}', 'duplicate_key'),
                      (b' ' * (MAX_EXCHANGE_BYTES + 1), 'size_budget'), (b'\xff', 'invalid_json')):
        with pytest.raises(CatalogError, match=code):
            parse_closure(bad)


def test_consumer_instances_use_exact_multi_root_closures_and_projection_reports_losses():
    raw = (Path(__file__).resolve().parents[1] / 'examples/ontology/parks/manufacturing.json').read_bytes()
    catalog = builtin_catalog()
    roots = ['built_environment', 'electrical', 'monitoring', 'operations']
    packages = [package(catalog.export(root), root) for root in roots]
    assembled = catalog_from_exchanges(packages)
    report = validate_instances(raw, assembled, rule_set='park-baseline')
    assert report['valid'], report['diagnostics']
    assert not validate_instances(raw, catalog_from_exchanges(packages[:-1]))['valid']
    changed_core = catalog.export('core')
    changed_core['modules'][0]['version'] = '0.2.0'
    with pytest.raises(CatalogError, match='exchange_dependency_conflict'):
        catalog_from_exchanges([*packages, package(changed_core, 'core')])

    projected = project_owl_classes(packages[1])
    nodes = {node['@id']: node for node in projected['document']['@graph']}
    cabinet, = (node for iri, node in nodes.items() if iri.endswith(':distribution_cabinet'))
    assert projected['partial'] and cabinet['@type'] == 'owl:Class'
    assert cabinet['rdfs:subClassOf']['@id'] in nodes
    assert any(item['path'].endswith('/properties/rated_voltage') for item in projected['omissions'])
    assert any(item['code'] == 'relation_and_constraints_not_projected' for item in projected['omissions'])
    with pytest.raises(CatalogError):
        parse_closure(canonical_bytes(projected['document']))
