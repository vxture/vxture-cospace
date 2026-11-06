import json
from fastapi.testclient import TestClient
from test_preview_publications import fixture
from test_preview_inputs import source
from packages.data.preview_inputs import PreviewInputs
from packages.service.preview_publications import PreviewPublications
from packages.service.preview_lineage import lineage
from experiments.scripts.serve_nyu_flow_preview import create_app


def prepared(tmp_path):
    initial,jobs=fixture(tmp_path)
    snapshot,tracking=source(tmp_path)
    catalog=PreviewInputs(tmp_path/'catalog'); registration=catalog.register('office',snapshot,tracking)
    jobs.inputs=catalog
    binding={k:v for k,v in registration.items() if k not in ('snapshot','tracking')}
    root=jobs.root/'build-one'; path=root/'output'/'model.json'
    manifest=json.loads(path.read_bytes()); manifest['source']={
        'snapshot_sha256':binding['snapshot_sha256'],'tracking_sha256':binding['tracking_sha256'],
        'input_binding':binding}
    path.write_text(json.dumps(manifest),encoding='utf-8')
    job=json.loads((root/'job.json').read_bytes()); job.update(input_id=registration['id'],input_binding=binding)
    (root/'job.json').write_text(json.dumps(job),encoding='utf-8')
    jobs.select('build-one',0); pubs=PreviewPublications(jobs); record=pubs.publish('build-one',1)
    return initial,jobs,pubs,record,registration


def test_full_lineage_is_bound_and_read_only(tmp_path):
    initial,jobs,pubs,record,registration=prepared(tmp_path)
    selection=jobs.selection(); before={p.name:p.read_bytes() for p in (pubs.root/record['id']).iterdir()}
    with TestClient(create_app(initial,jobs)) as client:
        report=client.get(record['preview_url']+'api/lineage').json()
        assert [n['status'] for n in report['nodes']]==['matched']*4
        assert report['nodes'][0]['id']==registration['id']
        assert len(report['relationships'])==3 and report['robot_ready'] is False
        # The common distribution gate rejects invalid publication IDs before routing.
        assert client.get('/publications/preview-invalid/api/lineage').status_code==404
    assert jobs.selection()==selection
    assert {p.name:p.read_bytes() for p in (pubs.root/record['id']).iterdir()}==before


def test_changed_registry_and_job_do_not_get_matched(tmp_path):
    _,jobs,pubs,record,registration=prepared(tmp_path)
    path=jobs.inputs.root/(registration['id']+'.json')
    changed=json.loads(path.read_bytes()); changed['label']='changed'
    path.write_text(json.dumps(changed),encoding='utf-8')
    job_path=jobs.root/'build-one'/'job.json'
    job=json.loads(job_path.read_bytes()); job['input_id']='wrong'
    job_path.write_text(json.dumps(job),encoding='utf-8')
    report=lineage(pubs,record['id'])
    assert [n['status'] for n in report['nodes']]==['mismatch','mismatch','matched','matched']
    path.unlink(); job_path.unlink()
    assert [n['status'] for n in lineage(pubs,record['id'])['nodes']]==['missing','missing','matched','matched']


def test_legacy_publication_does_not_infer_registration(tmp_path):
    _,jobs=fixture(tmp_path); jobs.select('build-one',0)
    pubs=PreviewPublications(jobs); record=pubs.publish('build-one',1)
    report=lineage(pubs,record['id'])
    assert report['nodes'][0]['status']=='missing' and report['nodes'][0]['id'] is None
    assert report['nodes'][1]['status']=='matched'
