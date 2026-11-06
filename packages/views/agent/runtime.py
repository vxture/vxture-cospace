"""R0 synthetic runtime contract. External fixed source required; no activation."""
from pathlib import Path
import ntpath
import uuid

from packages.data.imports import canonical, sha
from packages.data.structure import LiteralIntegerValidator
from packages.infrastructure.files import bounded_read, relative, safe_path, MAX_TOTAL
from packages.service.sample import inspect_package, read_json


SCHEMA = Path(__file__).resolve().parents[3] / 'contracts/schemas/agent-package-v0.1.schema.json'
SUPPORTED = {('occupancy', 'synthetic-regions/0.2'), ('semantics', 'synthetic-objects/0.1'),
             ('ontology', 'synthetic-ontology/0.1')}


class PackageError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def fail(code, message):
    raise PackageError(code, message)


def source_details(source):
    _, data = inspect_package(safe_path(source))
    if data['coverage'] is None:
        fail('unsupported_source', 'spatial synthetic bundle 0.2 required')
    release, truth = data['release'], data['truth']
    for ref in release['views']:
        raw = bounded_read(Path(source) / relative(ref['path']))
        view = read_json(raw)
        if view['view_kind'] == 'machine':
            binding = {'scene_id': release['scene_id'], 'release_id': release['release_id'],
                       'truth_version_id': truth['truth_version_id'], 'view_version_id': view['view_version_id'],
                       'view_kind': 'machine', 'package_sha256': data['package_sha256'],
                       'release_sha256': data['release_sha256'], 'truth_sha256': release['source_truth']['sha256'],
                       'view_sha256': sha(raw)}
            return binding, data
    fail('unsupported_source', 'machine view missing')


def build(source, destination):
    source, destination = safe_path(source), safe_path(destination)
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        fail('unsafe_path', 'source and output overlap')
    binding, data = source_details(source)
    components = []
    contents = {}
    for identity, role, encoding, ref, deps in (
        ('coverage', 'occupancy', 'synthetic-regions/0.2', data['truth']['coverage'], []),
        ('ontology', 'ontology', 'synthetic-ontology/0.1', data['truth']['ontology_ref'], []),
        ('objects', 'semantics', 'synthetic-objects/0.1', data['truth']['objects'], ['ontology'])):
        raw = bounded_read(source / relative(ref['path']))
        if sha(raw) != ref['sha256']:
            fail('content_mismatch', 'source changed during export')
        name = identity + '.json'
        contents[name] = raw
        components.append({'component_id': identity, 'role': role, 'encoding': encoding,
                           'required': True, 'depends_on': deps,
                           'member': {'path': name, 'bytes': len(raw), 'sha256': sha(raw)}})
    manifest = {'schema_version': 'cospace.agent-package/0.1', 'package_id': 'agent-' + uuid.uuid4().hex,
                'data_kind': 'synthetic', 'source': binding, 'frame': data['truth']['frame'],
                'scope': data['truth']['target_scope'], 'profile': 'synthetic-region-reading/0.1',
                'validity': 'unverified_sample_only', 'components': components}
    destination.mkdir(parents=True, exist_ok=False)
    for name, raw in contents.items():
        (destination / name).write_bytes(raw)
    (destination / 'agent-package.json').write_bytes(canonical(manifest))
    return verify(destination, source)


def verify(root, source):
    root = safe_path(root)
    raw = bounded_read(root / 'agent-package.json')
    manifest = read_json(raw)
    schema = read_json(SCHEMA.read_bytes())
    errors = list(LiteralIntegerValidator(schema).iter_errors(manifest))
    if errors:
        error = errors[0]
        fail('structure_error', '/' + '/'.join(map(str, error.absolute_path)) + ': ' + error.message)
    binding, data = source_details(source)
    if manifest['source'] != binding:
        fail('source_mismatch', 'fixed source identity or digest differs')
    if manifest['frame'] != data['truth']['frame'] or manifest['scope'] != data['truth']['target_scope']:
        fail('coordinate_mismatch', 'R0 requires exact source frame and full scope')
    components = manifest['components']
    by_id = {item['component_id']: item for item in components}
    if len(by_id) != len(components):
        fail('duplicate_component', 'component identity repeated')
    seen = {'agent-package.json'}
    total = len(raw)
    for item in components:
        member = item['member']
        name = str(relative(member['path']))
        if any(ntpath.isreserved(part) for part in relative(name).parts):
            fail('unsafe_path', 'reserved Windows member path')
        if name.casefold() in seen:
            fail('unsafe_path', 'duplicate or case-colliding member')
        seen.add(name.casefold())
        content = bounded_read(root / name)
        total += len(content)
        if total > MAX_TOTAL:
            fail('input_limit', 'runtime package exceeds synthetic total limit')
        if len(content) != member['bytes'] or sha(content) != member['sha256']:
            fail('content_mismatch', 'member digest or size differs: ' + name)
        if any(dep not in by_id for dep in item['depends_on']):
            fail('missing_dependency', 'dependency absent')
    visited, active = set(), set()
    def visit(identity):
        if identity in active:
            fail('dependency_cycle', 'component dependency cycle')
        if identity in visited:
            return
        active.add(identity)
        for dep in by_id[identity]['depends_on']:
            visit(dep)
        active.remove(identity)
        visited.add(identity)
    for identity in by_id:
        visit(identity)
    usable = set()
    for identity in visited:
        item = by_id[identity]
        if (item['role'], item['encoding']) in SUPPORTED:
            usable.add(identity)
        elif item['required']:
            fail('unsupported_component', 'unknown required role or encoding')
    for _ in components:
        usable = {identity for identity in usable if set(by_id[identity]['depends_on']) <= usable}
    if any(item['required'] and item['component_id'] not in usable for item in components):
        fail('unsupported_dependency', 'required component depends on unusable component')
    expected = {'occupancy': data['truth']['coverage']['sha256'],
                'semantics': data['truth']['objects']['sha256'],
                'ontology': data['truth']['ontology_ref']['sha256']}
    for role, digest in expected.items():
        items = [item for item in components if item['role'] == role and item['component_id'] in usable]
        if len(items) != 1 or not items[0]['required'] or items[0]['member']['sha256'] != digest:
            fail('profile_mismatch', 'profile requires exact source component: ' + role)
        if role == 'semantics' and items[0]['depends_on'] != [next(i['component_id'] for i in components if i['role'] == 'ontology' and i['component_id'] in usable)]:
            fail('profile_mismatch', 'semantic component must depend on ontology')
    return {'passed': True, 'package_id': manifest['package_id'], 'package_sha256': sha(raw),
            'source': binding, 'verified_bytes': total, 'usable_components': sorted(usable),
            'skipped_components': sorted(set(by_id) - usable), 'data_kind': 'synthetic',
            'real_release_ready': False, 'robot_ready': False, 'validity': manifest['validity']}
