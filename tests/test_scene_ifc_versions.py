import json

import pytest

from packages.data.ifc_inspection import inspect_ifc
from packages.data.ifc_workspace import IfcWorkspace
from packages.data.scene_attachments import SceneAttachments
from packages.lifecycle.scene_ifc_versions import ParseFailed, SceneIfcVersions, validate_version_storage, write_atomic
from test_ifc_inspection import fake_reader
from test_scene_attachments import catalog


@pytest.fixture
def scene(tmp_path):
    inputs, space = catalog(tmp_path)
    return SceneAttachments(inputs), space


def register(scene, tmp_path, name, data):
    attachments, space = scene
    source = tmp_path / name
    source.write_bytes(data)
    return attachments.register(source, space, name, 'usr_test')['attachment']['id']


def parse_fixture(source, output, digest):
    def reader(path):
        metadata, rows = fake_reader(path)
        metadata['structure'] = {'profile': 'cospace.ifc-structure-candidate/0.1',
                                 'assessment': 'unverified', 'data_kind': 'ifc_design_candidate',
                                 'entities': [{'entity_id': 'wall', 'geometry_product_id': 'wall',
                                               'ifc_type': 'IfcWall', 'role': 'wall'}], 'relations': []}
        return metadata, rows
    return inspect_ifc(source, output, expected_sha256=digest, reader=reader)


def test_versions_are_inactive_until_selected_and_rollback_reuses_existing_bytes(scene, tmp_path):
    attachments, space = scene
    store = SceneIfcVersions(attachments)
    records = []
    for n in (1, 2):
        identity = register(scene, tmp_path, f'plan{n}.ifc', f'fixture-{n}'.encode())
        task, created = store.enqueue(space, identity, 'usr_one')
        assert created
        assert store.enqueue(space, identity, 'usr_two') == (task, False)
        assert store.run(space, task['id'], parse_fixture)
        assert not store.run(space, task['id'], parse_fixture)
        ready = store.listing(space)['tasks'][task['id']]
        assert ready['state'] == 'ready'
        records.append(ready)
    a, b = records
    workspace = IfcWorkspace(attachments.inputs.directory, None, versions=store)
    assert workspace.directory_view(space)['configured'] is False
    assert store.resolve(space, catalog_sha256=a['catalog_sha256']) is None
    assert store.resolve(space, catalog_sha256=a['catalog_sha256'], include_pending=True) is not None
    original = store.activate(space, a['id'], expected_revision=0, actor='usr_one')
    assert store.resolve(space) == original
    with pytest.raises(ValueError, match='current_changed'):
        store.activate(space, b['id'], expected_revision=0, actor='usr_two')
    latest = store.activate(space, b['id'], expected_revision=1, actor='usr_two')
    assert store.resolve(space) == latest
    assert store.resolve(space, catalog_sha256=original.catalog_sha256) == original
    assert workspace.directory_view(space)['catalog_sha256'] == latest.catalog_sha256
    assert workspace.structure_view(space, original.catalog_sha256)['declared_role_counts'] == {'wall': 1}
    with pytest.raises(ValueError, match='ifc_catalog_changed'):
        workspace.structure_view(space, '0'*64)
    assert store.activate(space, a['id'], expected_revision=2, actor='usr_one') == original
    assert store.listing(space)['revision'] == 3
    assert [s['to'] for s in store.listing(space)['switches']] == [a['id'], b['id'], a['id']]
    config = tmp_path/'scene-ifc.json'
    write_atomic(config, {'profile':'cospace.scene-ifc-bindings/0.1','bindings':[original.model_dump()]})
    structure = IfcWorkspace(attachments.inputs.directory, None, config).structure_view(space, original.catalog_sha256)
    assert structure['declared_role_counts'] == {'wall': 1}
    assert structure['alignment_verified'] is False


def test_failed_and_interrupted_tasks_require_explicit_retry(scene, tmp_path):
    attachments, space = scene
    store = SceneIfcVersions(attachments)
    task, _ = store.enqueue(space, register(scene, tmp_path, 'sample.ifc', b'fixture'), 'usr_one')
    identity = task['id']

    def timeout(*args):
        raise ParseFailed('parse_timeout')

    assert not store.run(space, identity, timeout)
    assert store.listing(space)['tasks'][identity]['error'] == 'parse_timeout'
    assert not store.enqueue(space, task['attachment_id'], 'usr_one')[1]
    with pytest.raises(ValueError, match='not_ready'):
        store.activate(space, identity, expected_revision=0, actor='usr_one')
    second, created = store.enqueue(space, task['attachment_id'], 'usr_two', retry=True)
    assert created and second['attempt'] != task['attempt']
    path = store.root / space / 'versions.json'
    value = json.loads(path.read_bytes())
    value['tasks'][identity].update(state='running', lease_until=0)
    write_atomic(path, value)
    assert store.listing(space)['tasks'][identity]['error'] == 'worker_interrupted'
    assert store.enqueue(space, task['attachment_id'], 'usr_two', retry=True)[1]
    assert store.run(space, identity, parse_fixture)
    assert store.resolve(space) is None


def test_non_ifc_and_cross_scene_attachment_are_not_job_inputs(scene, tmp_path):
    attachments, space = scene
    store = SceneIfcVersions(attachments)
    text = register(scene, tmp_path, 'readme.txt', b'hello')
    with pytest.raises(ValueError, match='ifc_attachment_required'):
        store.enqueue(space, text, 'usr_one')
    other_inputs = attachments.inputs
    project = other_inputs.directory.read('space', space)['project_id']
    other = other_inputs.directory.create('space', 'Other', project)['id']
    identity = register((attachments, other), tmp_path, 'other.ifc', b'other file')
    with pytest.raises(ValueError, match='attachment_evidence_unavailable'):
        store.enqueue(space, identity, 'usr_one')
    assert store.listing(space)['tasks'] == {}


def test_backup_rejects_damaged_ready_version_and_invalid_pointer(scene, tmp_path):
    attachments, space = scene
    store = SceneIfcVersions(attachments)
    attachment = register(scene, tmp_path, 'source.ifc', b'fixture')
    task, _ = store.enqueue(space, attachment, 'usr_one')
    assert store.run(space, task['id'], parse_fixture)
    validate_version_storage(attachments.inputs.root)
    folder, path = store._paths(space)
    value = json.loads(path.read_bytes())
    write_atomic(path, value | {'current': task['id']})
    with pytest.raises(ValueError, match='current_pointer_invalid'):
        validate_version_storage(attachments.inputs.root)
    write_atomic(path, value)
    (folder / task['attempt'] / 'e00001.npz').write_bytes(b'wrong mesh')
    with pytest.raises(ValueError, match='ifc_mesh_changed'):
        validate_version_storage(attachments.inputs.root)
