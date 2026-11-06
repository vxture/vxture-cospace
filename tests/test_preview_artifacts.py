import json
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from test_preview_lineage import prepared
from test_preview_publication_changes import published
from test_preview_space_flow import setup
from packages.data.preview_artifacts import artifact_catalog
from packages.construction.preview_model import digest
from packages.service.preview_publications import PreviewPublications
from experiments.scripts.serve_nyu_flow_preview import create_app


def inventory(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_catalog_classifies_links_and_never_polls_or_exports(tmp_path,monkeypatch):
    _,jobs,pubs,record,registration=prepared(tmp_path)
    monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('read catalog must not poll'))
    monkeypatch.setattr('packages.views.agent.preview_offline.export_bundle',lambda *args:pytest.fail('must not export'))
    before=inventory(tmp_path)
    report=artifact_catalog(pubs)
    assert report['counts']=={'input':1,'candidate':2,'publication':1,'offline_package':1}
    items={i['key']:i for i in report['items']}
    assert items['input:'+registration['id']]['integrity']=='record_only'
    assert items['candidate:build-one']['selected'] and report['selection_status']=='matched'
    assert items['candidate:build-one']['classification']=='geometry_candidate'
    assert items['publication:'+record['id']]['integrity']=='snapshot_verified'
    assert items['offline_package:'+record['id']]['state']=='export_on_request'
    assert items['offline_package:'+record['id']]['integrity']=='not_generated'
    assert 'sha256' not in items['offline_package:'+record['id']]
    assert all(r['status']=='matched' for r in report['relations'] if r['from']!='candidate:build-two')
    assert not report['source_files_rechecked'] and not report['consumer_state_checked']
    assert str(registration['snapshot']) not in json.dumps(report)
    assert inventory(tmp_path)==before


def test_semantic_candidates_and_published_snapshots_keep_separate_items(tmp_path):
    _,_,_,_,_,pubs,old,new,body=published(tmp_path)
    report=artifact_catalog(pubs,body['space_id'])
    items={i['key']:i for i in report['items']}
    assert items['candidate:'+new['candidate_id']]['classification']=='semantic_candidate'
    assert items['candidate:'+new['candidate_id']]['selected']
    assert items['candidate:'+old['candidate_id']]['selected'] is False
    assert any(r['relation']=='annotated_from' and r['status']=='matched' for r in report['relations'])
    assert report['counts']['publication']==report['counts']['offline_package']==2
    assert all(r['to'] is None or r['to'] in items for r in report['relations'])


def test_missing_candidate_and_input_keep_fixed_publication_and_export(tmp_path):
    _,jobs,pubs,record,registration=prepared(tmp_path)
    shutil.rmtree(jobs.root/'build-one');(jobs.inputs.root/(registration['id']+'.json')).unlink()
    report=artifact_catalog(pubs)
    assert report['counts']=={'input':0,'candidate':1,'publication':1,'offline_package':1}
    assert report['selection_status']=='missing_or_mismatch'
    relations=[r for r in report['relations'] if r['from']=='publication:'+record['id']]
    assert {r['relation'] for r in relations}=={'sourced_from','published_from'}
    assert all(r['status']=='missing' and r['to'] is None for r in relations)


@pytest.mark.parametrize('kind',['candidate','publication','input','selection'])
def test_broken_binding_not_shown_as_valid(tmp_path,kind):
    _,jobs,pubs,record,registration=prepared(tmp_path)
    if kind=='candidate':(jobs.root/'build-one/output/agent.npz').write_bytes(b'bad')
    elif kind=='publication':(pubs.root/record['id']/'agent.npz').write_bytes(b'bad')
    elif kind=='input':
        path=jobs.inputs.root/(registration['id']+'.json');r=json.loads(path.read_bytes());r['label']='changed';path.write_text(json.dumps(r))
    else:
        path=jobs.root/'selection.json';r=json.loads(path.read_bytes());r['model_manifest_sha256']='0'*64;path.write_text(json.dumps(r))
    report=artifact_catalog(pubs);items={i['key']:i for i in report['items']}
    if kind=='candidate':
        assert items['candidate:build-one']['integrity']=='unavailable' and not items['candidate:build-one']['resources']
        assert items['publication:'+record['id']]['integrity']=='snapshot_verified'
    elif kind=='publication':
        assert items['publication:'+record['id']]['integrity']=='unavailable'
        assert report['counts']['offline_package']==0
    elif kind=='input':
        assert next(r for r in report['relations'] if r['from']=='candidate:build-one')['status']=='mismatch'
    else:assert not any(i['selected'] for i in report['items'])


def test_scoped_catalog_no_legacy_fallback_cross_space_or_paths(tmp_path):
    initial,jobs,directory,(a,b)=setup(tmp_path);pubs=PreviewPublications(jobs)
    jobs.select('build-one',0,a['id']);pubs.publish('build-one',1,a['id'])
    with TestClient(create_app(initial,jobs,space_directory=directory)) as client:
        report=client.get('/api/artifacts',params={'space_id':a['id']}).json()
        assert report['space_id']==a['id'] and report['counts']['candidate']==1
        assert all(i['record_id']!='build-two' for i in report['items'])
        assert client.get('/api/artifacts').json()['items']==[]
        assert client.get('/api/artifacts?space_id=unknown').status_code==404
        assert client.get('/api/artifacts',params={'space_id':b['id']}).json()['counts']['publication']==0
    # Explicit bad cross-space semantic parent must never become a navigable link.
    path=jobs.root/'build-one/output/model.json';m=json.loads(path.read_bytes())
    m['source']['input_binding']['id']='input-'+'0'*16;path.write_text(json.dumps(m))
    assert all(r['to'] is None for r in artifact_catalog(pubs,a['id'])['relations'] if r['relation']=='built_from')


def test_running_failed_jobs_are_counts_not_candidates_and_read_does_not_create_selection_dir(tmp_path):
    _,jobs,_,(a,_)=setup(tmp_path);pubs=PreviewPublications(jobs)
    for i,state in enumerate(['running','queued','failed','interrupted']):
        root=jobs.root/f'build-state{i}';root.mkdir()
        (root/'job.json').write_text(json.dumps({'id':root.name,'state':state,'space_id':a['id'],'project_id':a['project_id']}))
    before=inventory(tmp_path)
    report=artifact_catalog(pubs,a['id'])
    assert report['counts']['candidate']==1
    assert all(report['job_counts'][s]==1 for s in ['running','queued','failed','interrupted'])
    assert not (jobs.root/'space-selections').exists() and inventory(tmp_path)==before


def test_corrupt_record_fails_closed_and_empty_service(tmp_path):
    initial,jobs,pubs,_,_=prepared(tmp_path)
    (jobs.root/'build-one/job.json').write_bytes(b'{')
    with TestClient(create_app(initial,jobs)) as client:
        assert client.get('/api/artifacts').status_code==409
    with TestClient(create_app(initial)) as client:assert client.get('/api/artifacts').status_code==503


def test_pending_records_are_not_committed_artifacts(tmp_path):
    _,jobs,pubs,_,_=prepared(tmp_path)
    pending=jobs.root/'.pending-build-incomplete';pending.mkdir();(pending/'job.json').write_bytes(b'{')
    assert artifact_catalog(pubs)['counts']['candidate']==2


def test_catalog_does_not_recheck_or_repair_changed_source_files(tmp_path):
    _,_,pubs,_,registration=prepared(tmp_path)
    (Path(registration['snapshot'])/'raw/d.pgm').write_bytes(b'changed source')
    before=inventory(tmp_path);report=artifact_catalog(pubs)
    assert report['source_files_rechecked'] is False
    assert next(i for i in report['items'] if i['kind']=='input')['integrity']=='record_only'
    assert inventory(tmp_path)==before


def test_publication_cross_space_candidate_reference_is_not_navigable(tmp_path):
    _,jobs,_,(a,b)=setup(tmp_path);pubs=PreviewPublications(jobs)
    jobs.select('build-one',0,a['id']);record=pubs.publish('build-one',1,a['id'])
    root=pubs.root/record['id'];path=root/'model.json';model=json.loads(path.read_bytes())
    model['id']='build-two';path.write_text(json.dumps(model))
    record.update(candidate_id='build-two',model_manifest_sha256=digest(path))
    record['files']['model.json']={'sha256':digest(path),'bytes':path.stat().st_size}
    (root/'publication.json').write_text(json.dumps(record))
    report=artifact_catalog(pubs,a['id'])
    relation=next(r for r in report['relations'] if r['relation']=='published_from')
    assert relation['status']=='mismatch' and relation['to'] is None
    assert 'build-two' not in json.dumps(report)


def test_api_contract_schema(tmp_path):
    initial,jobs,pubs,_,_=prepared(tmp_path)
    schema=json.loads(Path('contracts/schemas/preview-artifacts-v0.1.schema.json').read_bytes())
    Draft202012Validator.check_schema(schema)
    with TestClient(create_app(initial,jobs)) as client:
        response=client.get('/api/artifacts');assert response.status_code==200
        Draft202012Validator(schema).validate(response.json())
