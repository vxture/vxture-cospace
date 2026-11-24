import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest


spec = importlib.util.spec_from_file_location(
    'ontology_checkpoint', Path(__file__).resolve().parents[1] / 'deploy/linux/backup_ontology.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_wal_backup_can_restore_committed_definition_without_changing_source(tmp_path):
    runtime = tmp_path / 'data/business/runtime/preview-directory'
    runtime.mkdir(parents=True)
    source = runtime / module.DATABASES[1]
    with sqlite3.connect(source) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('CREATE TABLE revisions (id INTEGER, definition TEXT)')
        writer.execute("INSERT INTO revisions VALUES (1, 'frozen-definition')")
        writer.commit()
        target = module.checkpoint(tmp_path, [{'service': 'workbench', 'image_id': 'sha256:old'}])
        writer.execute("INSERT INTO revisions VALUES (2, 'later-definition')")
        writer.commit()
        with sqlite3.connect(target / source.name) as restored:
            assert restored.execute('SELECT * FROM revisions').fetchall() == [(1, 'frozen-definition')]
        assert writer.execute('SELECT COUNT(*) FROM revisions').fetchone() == (2,)
    manifest = json.loads((target / 'manifest.json').read_text())
    assert manifest['complete'] is True
    assert manifest['databases'][module.DATABASES[0]] == 'absent'
    assert manifest['images'][0]['image_id'] == 'sha256:old'


def test_corrupt_database_blocks_deployment_with_incomplete_checkpoint(tmp_path):
    runtime = tmp_path / 'data/business/runtime/preview-directory'
    runtime.mkdir(parents=True)
    (runtime / module.DATABASES[0]).write_bytes(b'corrupt database')
    with pytest.raises(sqlite3.DatabaseError):
        module.checkpoint(tmp_path, [])
    manifests = list((tmp_path / 'backups').glob('*/manifest.json'))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text())['complete'] is False


def test_publication_lifecycle_checkpoint_preserves_rollback_quarantine(tmp_path):
    runtime=tmp_path/'data/business/runtime'
    (runtime/'preview-directory').mkdir(parents=True)
    source=runtime/module.CONTROL_DATABASE
    with sqlite3.connect(source) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('CREATE TABLE controls (artifact TEXT, state TEXT)')
        writer.execute("INSERT INTO controls VALUES ('publication:fixed', 'paused')")
        writer.commit()
        target=module.checkpoint(tmp_path,[])
        writer.execute("UPDATE controls SET state='active'");writer.commit()
        with sqlite3.connect(target/source.name) as restored:
            assert restored.execute('SELECT state FROM controls').fetchall()==[('paused',)]
    manifest=json.loads((target/'manifest.json').read_text())
    assert manifest['complete'] and manifest['databases'][module.CONTROL_DATABASE]=='verified'


def test_corrupt_lifecycle_database_blocks_service_replacement(tmp_path):
    runtime=tmp_path/'data/business/runtime';(runtime/'preview-directory').mkdir(parents=True)
    (runtime/module.CONTROL_DATABASE).write_bytes(b'corrupt lifecycle')
    with pytest.raises(sqlite3.DatabaseError):module.checkpoint(tmp_path,[])
    manifest=next((tmp_path/'backups').glob('*/manifest.json'))
    assert not json.loads(manifest.read_text())['complete']


def test_registration_checkpoint_restores_fixed_approved_and_adopted_revision(tmp_path):
    from packages.service.scene_registrations import SceneRegistrations
    from test_scene_registrations import approval, command, source, service
    document = json.loads(Path('contracts/examples/spatial-registration-campus.json').read_text(encoding='utf-8'))
    document['synthetic'] = False
    runtime = tmp_path / 'data/business/runtime/preview-directory'
    writer, bound = service(runtime), source(document)
    writer.change(bound, command(document))
    writer.change(bound, command(document, 'submit', 1, 2))
    service(runtime, 'reviewer').change(bound, command(document, 'approve', 2, 3,
        approval=approval(document)), can_review=True)
    writer.change(bound, command(document, 'adopt', 3, 4))
    checkpoint = module.checkpoint(tmp_path, [])
    writer.change(bound, command(document, 'clear_adoption', 4, 5))
    restored = SceneRegistrations(checkpoint, 'workspace', 'reader', None).read(bound)
    assert restored['revision'] == 4 and restored['adopted']['revision'] == 3
    assert restored['adopted']['reviewed_by'] == 'reviewer'
    assert writer.read(bound)['adopted'] is None


def test_input_coordinate_checkpoint_preserves_wal_revision_history(tmp_path):
    from packages.data.input_coordinates import InputCoordinates
    from packages.data.preview_inputs import PreviewInputs
    from test_input_coordinates import change
    from test_input_uploads import catalog_at
    from test_preview_pointcloud import specimen
    runtime = tmp_path / 'data/business/runtime'
    (runtime / 'preview-directory').mkdir(parents=True)
    fixture, spaces = catalog_at(tmp_path / 'fixture')
    catalog = PreviewInputs(runtime / 'preview-inputs', fixture.directory)
    original = catalog.register('legacy', specimen(tmp_path / 'fixture'), None, spaces[0], 'ply_pointcloud')
    store = InputCoordinates(catalog)
    store.change(original['id'], change(original), 'engineer')
    with sqlite3.connect(store.path) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        store.change(original['id'], change(original, expected_revision=1, request_id='b'*32,
            coordinates=change(original).coordinates.model_dump() | {'axes':['右','前','上']}), 'engineer')
        target = module.checkpoint(tmp_path, [])
    restored = InputCoordinates(catalog)
    restored.path = target / module.COORDINATE_DATABASE
    assert len(restored.events(original)) == 2
    assert restored.effective(original)['axes'] == ['右','前','上']
    manifest = json.loads((target / 'manifest.json').read_text())
    assert manifest['complete'] and manifest['databases'][module.COORDINATE_DATABASE] == 'verified'


def test_corrupt_input_coordinate_history_blocks_service_replacement(tmp_path):
    runtime = tmp_path / 'data/business/runtime'
    (runtime / 'preview-directory').mkdir(parents=True)
    (runtime / 'preview-inputs').mkdir()
    (runtime / 'preview-inputs' / module.COORDINATE_DATABASE).write_bytes(b'corrupt coordinates')
    with pytest.raises(sqlite3.DatabaseError):
        module.checkpoint(tmp_path, [])
    manifest = next((tmp_path / 'backups').glob('*/manifest.json'))
    assert not json.loads(manifest.read_text())['complete']


def test_business_project_checkpoint_restores_project_and_audit_before_later_changes(tmp_path):
    from dataclasses import replace
    from packages.lifecycle.preview_spaces import PreviewSpaces
    from packages.lifecycle.workspace_projects import WorkspaceProjects, ProjectChange, ProjectQuery
    from packages.service.space_access import SpaceAccessPolicy
    from test_space_access import principal
    runtime = tmp_path / 'data/business/runtime/preview-directory'
    runtime.mkdir(parents=True)
    directory = PreviewSpaces(runtime)
    projects = WorkspaceProjects(directory)
    user = replace(principal(), governance_roles=('workspace:owner',))
    policy = SpaceAccessPolicy(bindings=[], grants=[])
    command = {'action': 'create', 'name': 'Synthetic project', 'request_id': 'a'*32,
               'expected_revision': 0, 'reason': 'Checkpoint fixture'}
    first = projects.change(user, policy, ProjectChange.validate_python(command))
    target = module.checkpoint(tmp_path, [])
    projects.change(user, policy, ProjectChange.validate_python(command | {
        'action': 'update', 'project_id': first['project_id'], 'name': 'Later name',
        'request_id': 'b'*32, 'expected_revision': 1}))
    restored = WorkspaceProjects(directory)
    restored.path = target / 'business-projects.sqlite3'
    assert restored.read(user, policy, ProjectQuery())['items'][0]['name'] == 'Synthetic project'
    assert restored.read(user, policy, ProjectQuery(view='history'))['total'] == 1
    assert projects.read(user, policy, ProjectQuery())['items'][0]['name'] == 'Later name'
    manifest = json.loads((target / 'manifest.json').read_text())
    assert manifest['complete'] and manifest['databases']['business-projects.sqlite3'] == 'verified'
