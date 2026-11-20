"""Portable module integrity, semantics and extraction boundaries."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from packages.ontology.kernel import Catalog, CatalogError, builtin_catalog, canonical_bytes
from packages.ontology.kernel.catalog import MAX_BYTES


def modules():
    return builtin_catalog().export()['modules']


def module(values, identity):
    return next(value for value in values if value['module_id'] == identity)


def rebind(values):
    # Test fixtures with changed core definitions explicitly pin a new digest.
    for value in values:
        for reference in value['requires']:
            target = module(values, reference['module_id'])
            reference.update(version=target['version'], sha256=hashlib.sha256(canonical_bytes(target)).hexdigest())


def test_portable_catalog_and_exact_closure_roundtrip():
    catalog = builtin_catalog()
    data = catalog.describe()
    assert len(data['modules']) == 8
    assert data['status'] == 'draft'
    assert 'instance-validation' not in data['capabilities']
    exported = catalog.export('electrical')
    assert [m['module_id'] for m in exported['modules']] == ['core', 'electrical']
    reopened = Catalog.from_bytes(canonical_bytes(exported))
    assert reopened.export() == exported
    assert reopened.describe()['library_sha256'] == hashlib.sha256(canonical_bytes(exported)).hexdigest()
    assert catalog.describe() == Catalog(list(reversed(modules()))).describe()


def test_exports_are_detached_and_history_is_not_mutated():
    values = modules()
    catalog = Catalog(values)
    previous = catalog.describe()
    values[0]['title'] = 'changed'
    export = catalog.export()
    export['modules'][0]['concepts'].clear()
    catalog.describe()['modules'].clear()
    assert catalog.describe() == previous


def test_transitive_dependencies_and_references_are_exported_together():
    values = modules()
    water = module(values, 'water')
    electrical = module(values, 'electrical')
    electrical['requires'].append(dict(module_id='water', version=water['version'],
                                      sha256=hashlib.sha256(canonical_bytes(water)).hexdigest()))
    electrical['concepts']['pump_reference'] = deepcopy(water['concepts']['pump'])
    electrical['concepts']['pump_reference'].update(parent='water:pump', properties={})
    catalog = Catalog(values)
    assert [item['module_id'] for item in catalog.export('electrical')['modules']] == ['core', 'electrical', 'water']


@pytest.mark.parametrize('change,code', [
    (lambda values: module(values, 'electrical')['requires'][0].update(sha256='0' * 64), 'dependency_mismatch'),
    (lambda values: module(values, 'electrical')['requires'][0].update(version='9.0.0'), 'dependency_mismatch'),
    (lambda values: values.remove(module(values, 'core')), 'missing_dependency'),
    (lambda values: values.append(deepcopy(values[0])), 'duplicate_module'),
    (lambda values: module(values, 'electrical')['requires'].append(deepcopy(module(values, 'electrical')['requires'][0])), 'duplicate_dependency'),
    (lambda values: module(values, 'electrical')['concepts']['distribution_cabinet'].update(parent='water:pump'), 'unresolved_concept'),
    (lambda values: module(values, 'electrical')['relations']['supplies'].update(target_types=['core:missing']), 'unresolved_concept'),
    (lambda values: module(values, 'electrical').update(status='published'), 'unsupported_status'),
    (lambda values: module(values, 'electrical').update(profile='cospace.preview-ontology/0.2'), 'unsupported_profile'),
    (lambda values: module(values, 'electrical').update(scene_id='site-one'), 'invalid_fields'),
    (lambda values: module(values, 'electrical')['concepts']['distribution_cabinet']['properties']['rated_voltage'].update(data_type='string'), 'invalid_unit'),
    (lambda values: module(values, 'electrical')['concepts']['distribution_cabinet']['properties']['rated_voltage'].update(minimum=True), 'invalid_minimum'),
    (lambda values: module(values, 'electrical')['concepts']['distribution_cabinet']['properties']['rated_voltage'].update(minimum=10 ** 1000), 'invalid_minimum'),
    (lambda values: module(values, 'electrical')['concepts']['distribution_cabinet']['properties']['rated_voltage'].update(required='yes'), 'invalid_property'),
    (lambda values: module(values, 'built_environment')['relations']['adjacent_to'].update(target_types=['core:entity']), 'symmetric_endpoints_mismatch'),
])
def test_invalid_definitions_have_locatable_diagnostics(change, code):
    values = modules()
    change(values)
    with pytest.raises(CatalogError) as error:
        Catalog(values)
    assert error.value.code == code
    assert error.value.path.startswith('/modules/')


def test_core_cannot_depend_on_domain():
    values = modules()
    values = [value for value in values if value['module_id'] in ('core', 'water')]
    core = module(values, 'core')
    target = module(values, 'water')
    target['requires'] = []
    core['requires'] = [dict(module_id='water', version=target['version'], sha256=hashlib.sha256(canonical_bytes(target)).hexdigest())]
    with pytest.raises(CatalogError, match='core_depends_on_domain'):
        Catalog(values)


def test_inheritance_cycles_and_overrides_do_not_silently_change_meaning():
    values = modules()
    core = module(values, 'core')
    core['concepts']['entity']['parent'] = 'core:physical_object'
    rebind(values)
    with pytest.raises(CatalogError, match='inheritance_cycle'):
        Catalog(values)
    values = modules()
    module(values, 'electrical')['concepts']['distribution_cabinet']['properties']['name'] = deepcopy(module(values, 'core')['concepts']['entity']['properties']['name'])
    with pytest.raises(CatalogError, match='property_override_unsupported'):
        Catalog(values)


@pytest.mark.parametrize('raw,code', [
    (b'{"profile": "x", "profile": "y", "modules": []}', 'duplicate_key'),
    (b'[]', 'invalid_fields'),
    (b'\xff', 'invalid_json'),
    (b'{' * 2000, 'invalid_json'),
    (b' ' * (MAX_BYTES + 1), 'size_budget'),
    (b'{"profile":"other","modules":[]}', 'unsupported_profile'),
])
def test_input_budget_and_json_fail_closed(raw, code):
    with pytest.raises(CatalogError) as error:
        Catalog.from_bytes(raw)
    assert error.value.code == code


def test_non_finite_numbers_and_unknown_module():
    values = modules()
    module(values, 'electrical')['concepts']['distribution_cabinet']['properties']['rated_voltage']['minimum'] = float('nan')
    with pytest.raises(CatalogError, match='invalid_json'):
        Catalog(values)
    with pytest.raises(CatalogError, match='module_not_found'):
        builtin_catalog().export('missing')


def test_kernel_runs_without_repository_or_third_party_imports(tmp_path):
    parent = Path('packages/ontology').resolve()
    script = '''
import json,sys
sys.path.insert(0,sys.argv[1])
from kernel import builtin_catalog
catalog=builtin_catalog()
assert len(catalog.describe()['modules'])==8
assert not any(name=='packages' or name.startswith(('fastapi','pydantic','numpy','sqlalchemy')) for name in sys.modules)
print(json.dumps(catalog.export('electrical')))
'''
    result = subprocess.run([sys.executable, '-I', '-c', script, str(parent)], cwd=tmp_path,
                            capture_output=True, text=True, check=True)
    assert len(json.loads(result.stdout)['modules']) == 2


def test_standalone_cli_validation_and_safe_error(tmp_path):
    parent = str(Path('packages/ontology').resolve())
    command = [sys.executable, '-I', '-c', "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('kernel',run_name='__main__')", parent]
    result = subprocess.run(command + ['--module', 'water'], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert len(json.loads(result.stdout)['modules']) == 2
    result = subprocess.run(command + ['--library', str(tmp_path / 'missing-private-file.json')], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stderr) == {'error': 'library_unavailable', 'path': '/'}
    assert 'private-file' not in result.stderr
