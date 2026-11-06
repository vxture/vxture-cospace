"""Interactions across batch, source, candidate, release and an already-held package."""
import pytest
from fastapi.testclient import TestClient
from packages.data.preview_batches import BatchDraft, BatchChange
from packages.lifecycle.preview_control import PreviewControls
from packages.views.agent.preview_offline import OfflinePreview, export_bundle, sha
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_impact import seed
from test_preview_control import run, payload


def blocked(tmp_path):
    initial, jobs, directory, spaces, ontologies, pubs, old, new, input_id = seed(tmp_path)
    space = spaces[0]['id']
    batch = jobs.batches.create(BatchDraft(space_id=space, name='integration', origin='imported_sample', note='test'))
    for operation, members in [('replace_members', [input_id]), ('seal', None), ('disable', None)]:
        batch = jobs.batches.change(batch['id'], BatchChange(space_id=space, expected_revision=batch['revision'],
                                   operation=operation, input_ids=members, reason='test'))
    held = export_bundle(*pubs.read(new['id']))
    run(jobs.controls, pubs, space, 'input:' + input_id, 'disable_input')
    run(jobs.controls, pubs, space, 'candidate:' + old['candidate_id'], 'archive_candidate')
    run(jobs.controls, pubs, space, 'publication:' + new['id'], 'pause_distribution')
    return initial, jobs, directory, spaces, ontologies, pubs, old, new, input_id, batch, held


def test_release_restore_does_not_enable_ancestors_and_offline_survives(tmp_path, monkeypatch):
    initial, jobs, directory, spaces, ontologies, pubs, old, new, input_id, batch, held = blocked(tmp_path)
    space = spaces[0]['id']; key = 'publication:' + new['id']; selection = jobs.selection(space)
    consumer = OfflinePreview(held, new['id'], sha(held)); objects = consumer.objects()
    reopened = PreviewControls(jobs.root.parent, directory)
    assert reopened.read(space, key)['lifecycle_state'] == 'paused'
    with TestClient(create_app(initial, jobs, space_directory=directory, ontologies=ontologies)) as client:
        assert client.get(new['preview_url'] + 'offline.zip').status_code == 409
        assert consumer.objects() == objects
        run(reopened, pubs, space, key, 'restore')
        assert client.get(new['preview_url'] + 'offline.zip').content == held
        assert client.get(new['preview_url'] + 'api/objects').json() == objects
        assert reopened.read(space, 'input:' + input_id)['lifecycle_state'] == 'disabled'
        assert reopened.read(space, 'candidate:' + old['candidate_id'])['lifecycle_state'] == 'archived'
        assert jobs.batches.read(batch['id'], space)['state'] == 'disabled'
        with pytest.raises(ValueError, match='disabled_new_use'):
            jobs.start(input_id, space, batch['id'], batch['revision'])
        run(reopened, pubs, space, 'candidate:' + old['candidate_id'], 'restore')
        run(reopened, pubs, space, 'input:' + input_id, 'restore')
        with pytest.raises(ValueError, match='batch_not_sealed_or_disabled'):
            jobs.start(input_id, space, batch['id'], batch['revision'])
        restored = jobs.batches.change(batch['id'], BatchChange(space_id=space, expected_revision=batch['revision'], operation='restore', reason='test'))
        monkeypatch.setattr(jobs, '_launch', lambda registered,snapshot,tracking,ownership,input_id,batch_ref,*_: {'batch_ref': batch_ref})
        assert jobs.start(input_id, space, batch['id'], restored['revision'])['batch_ref']['admitted_revision'] == restored['revision']
        assert jobs.selection(space) == selection


def test_combined_state_missing_evidence_does_not_turn_restore_into_zero_reference(tmp_path):
    initial, jobs, directory, spaces, ontologies, pubs, old, new, input_id, batch, held = blocked(tmp_path)
    space = spaces[0]['id']; key = 'publication:' + new['id']; store = jobs.controls
    request = payload(store, pubs, space, key, 'restore'); before = store.read(space, key)
    path = jobs.inputs.root / (input_id + '.json'); raw = path.read_bytes()
    try:
        path.unlink()
        report = store.report(pubs, space, key)
        assert report['impact']['issues'] and not report['actions'][0]['allowed']
        with pytest.raises(ValueError, match='references_changed'):
            store.change(pubs, request)
        with pytest.raises(ValueError, match='operation_blocked'):
            run(store, pubs, space, key, 'restore')
        assert store.read(space, key) == before
        with TestClient(create_app(initial, jobs, space_directory=directory, ontologies=ontologies)) as client:
            assert client.get(new['preview_url'] + 'offline.zip').status_code == 409
    finally:
        path.write_bytes(raw)
    assert run(store, pubs, space, key, 'restore')['revision'] == 2
    assert export_bundle(*pubs.read(new['id'])) == held
