"""Runtime contract source binding and fail-closed component compatibility."""
import copy
import json
from pathlib import Path
import pytest

from packages.data.imports import canonical, sha
from packages.views.agent.runtime import build, verify, PackageError, SCHEMA
from scripts.build_sample import build as build_source
from jsonschema import Draft202012Validator


@pytest.fixture
def bundle(tmp_path):
    source, output = tmp_path / 'source', tmp_path / 'runtime'
    build_source(source, spatial=True)
    report = build(source, output)
    assert report['passed'] and not report['robot_ready']
    return source, output


def mutate(root, change):
    path = root / 'agent-package.json'
    value = json.loads(path.read_text())
    change(value)
    path.write_bytes(canonical(value))


def test_schema_and_roundtrip(bundle):
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text()))
    source, output = bundle
    report = verify(output, source)
    assert report['usable_components'] == ['coverage', 'objects', 'ontology']
    assert not report['skipped_components']
    assert sorted(p.name for p in output.iterdir()) == ['agent-package.json', 'coverage.json', 'objects.json', 'ontology.json']


@pytest.mark.parametrize('change,code', [
    (lambda m: m['source'].update(release_id='other'), 'source_mismatch'),
    (lambda m: m['frame'].update(unit='cm'), 'coordinate_mismatch'),
    (lambda m: m['scope'][1].__setitem__(0, 9), 'coordinate_mismatch'),
    (lambda m: m['components'][0].update(encoding='ESDF/unvalidated'), 'unsupported_component'),
    (lambda m: m['components'][0].update(depends_on=['missing']), 'missing_dependency'),
    (lambda m: m['components'][0].update(depends_on=['coverage']), 'dependency_cycle'),
    (lambda m: m['components'].append(copy.deepcopy(m['components'][0])), 'duplicate_component'),
    (lambda m: m['components'].pop(0), 'profile_mismatch'),
    (lambda m: m['components'][2].update(depends_on=[]), 'profile_mismatch'),
    (lambda m: m.update(validity='valid'), 'structure_error'),
])
def test_rejects_contract_changes(bundle, change, code):
    source, output = bundle
    mutate(output, change)
    with pytest.raises(PackageError) as error:
        verify(output, source)
    assert error.value.code == code


def test_missing_and_corrupt_member(bundle):
    source, output = bundle
    member = output / 'coverage.json'
    member.write_bytes(b'{}')
    with pytest.raises(PackageError, match='digest'):
        verify(output, source)
    member.unlink()
    with pytest.raises(ValueError):
        verify(output, source)


def test_rehashed_changed_component_still_rejected(bundle):
    source, output = bundle
    content = b'{}'
    (output / 'coverage.json').write_bytes(content)
    mutate(output, lambda m: m['components'][0]['member'].update(bytes=len(content), sha256=sha(content)))
    with pytest.raises(PackageError) as error:
        verify(output, source)
    assert error.value.code == 'profile_mismatch'


def test_optional_unknown_and_dependency_closure(bundle):
    source, output = bundle
    optional = {'component_id': 'extra', 'role': 'future', 'encoding': 'future/1', 'required': False,
                'depends_on': [], 'member': {'path': 'extra.json', 'bytes': 2, 'sha256': sha(b'{}')}}
    (output / 'extra.json').write_bytes(b'{}')
    mutate(output, lambda m: m['components'].append(optional))
    assert verify(output, source)['skipped_components'] == ['extra']
    mutate(output, lambda m: m['components'][0].update(depends_on=['extra']))
    with pytest.raises(PackageError) as error:
        verify(output, source)
    assert error.value.code == 'unsupported_dependency'


def test_traversal_and_case_collision(bundle):
    source, output = bundle
    mutate(output, lambda m: m['components'][0]['member'].update(path='../outside.json'))
    with pytest.raises(ValueError, match='logical path'):
        verify(output, source)
    mutate(output, lambda m: m['components'][0]['member'].update(path='ONTOLOGY.JSON'))
    # May fail content check before the case-collision check; never accepted.
    with pytest.raises(ValueError):
        verify(output, source)


def test_source_swap_and_output_overwrite_rejected(bundle, tmp_path):
    source, output = bundle
    other = tmp_path / 'other'
    build_source(other, spatial=True)
    def rename(name, document):
        if name == 'objects.json':
            document['objects'][0]['properties']['name'] = 'different source'
    changed = tmp_path / 'changed'
    build_source(changed, mutate=rename, spatial=True)
    with pytest.raises(PackageError) as error:
        verify(output, changed)
    assert error.value.code == 'source_mismatch'
    with pytest.raises(FileExistsError):
        build(source, output)
    with pytest.raises(PackageError):
        build(source, source / 'child')
