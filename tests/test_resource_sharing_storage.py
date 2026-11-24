"""Shared snapshots fail closed and travel with the project database backup."""
import json
import sqlite3

from test_resource_sharing import shared, grant, download
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_ontology_deployment_checkpoint import module as checkpoint_module


def test_deployment_checkpoint_freezes_grants_and_payload_together(shared, tmp_path):
    granted = grant(shared)
    source = shared['directory'].root/'business-projects.sqlite3'
    root = tmp_path/'deployment-fixture'
    runtime = root/'data/business/runtime/preview-directory'
    runtime.mkdir(parents=True)
    target_source = runtime/source.name
    with sqlite3.connect(source) as original, sqlite3.connect(target_source) as target:
        original.backup(target)
    checkpoint = checkpoint_module.checkpoint(root, [])
    with sqlite3.connect(target_source) as writer:
        writer.execute('UPDATE data_shared_versions SET payload=?', (b'later data',))
    with sqlite3.connect(checkpoint/source.name) as restored:
        assert restored.execute('SELECT payload FROM data_shared_versions').fetchone()[0] == shared['payload']
        assert json.loads(restored.execute('SELECT record FROM data_resource_grants').fetchone()[0])['id'] == granted['id']
        assert restored.execute('SELECT COUNT(*) FROM data_sharing_changes').fetchone()[0] == 1


def test_corrupt_download_permission_is_never_coerced_to_true(shared):
    granted = grant(shared)
    with sqlite3.connect(shared['directory'].root/'business-projects.sqlite3') as db:
        record=json.loads(db.execute('SELECT record FROM data_resource_grants').fetchone()[0])
        record['allow_download']='false'
        db.execute('UPDATE data_resource_grants SET record=?',(json.dumps(record),))
    sign_in(shared['secured'],'usr_other')
    assert download(shared,granted).status_code==503
    assert shared['client'].get('/api/data-resources',params={'project_id':shared['b']}).status_code==503


def test_corrupt_snapshot_cannot_expose_private_source_fields(shared):
    granted=grant(shared)
    with sqlite3.connect(shared['directory'].root/'business-projects.sqlite3') as db:
        record=json.loads(db.execute('SELECT record FROM data_shared_versions').fetchone()[0])
        record['space_id']=shared['scenes'][0]['id']
        db.execute('UPDATE data_shared_versions SET record=?',(json.dumps(record),))
    sign_in(shared['secured'],'usr_other')
    result=shared['client'].get('/api/data-sharing',params={'project_id':shared['b']})
    assert result.status_code==503 and shared['scenes'][0]['id'] not in result.text
    assert download(shared,granted).status_code==503
