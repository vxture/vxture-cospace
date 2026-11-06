"""Source binding integration using synthetic candidate geometry, not worker accuracy tests."""
import json
import pytest
from packages.data.input_uploads import InputUploads
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_batches import PreviewBatches, BatchDraft, BatchChange, batch_results
from packages.lifecycle.preview_scope import scope
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.preview_offline import OfflinePreview, export_bundle, sha
from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
from test_input_uploads import package
from test_preview_space_flow import setup


def bound_fixture(tmp_path):
    _,jobs,directory,spaces=setup(tmp_path)
    jobs.inputs=PreviewInputs(tmp_path/'catalog',directory);jobs.batches=PreviewBatches(jobs.inputs)
    uploaded=InputUploads(jobs.inputs).register(package(tmp_path),spaces[0]['id'],'uploaded RGB-D','engineer')
    record=jobs.inputs.read(uploaded['input']['id']);space=spaces[0]['id']
    batch=jobs.batches.create(BatchDraft(space_id=space,name='uploaded sample',origin='imported_sample',note='test fixture'))
    for operation,extra in [('replace_members',{'input_ids':[record['id']]}),('seal',{})]:
        batch=jobs.batches.change(batch['id'],BatchChange(space_id=space,expected_revision=batch['revision'],operation=operation,reason='test',**extra))
    # Candidate geometry is an existing unit fixture. Only its explicit source
    # bindings are attached here; real worker execution is covered by P10 replay.
    binding={k:v for k,v in record.items() if k not in ('snapshot','tracking')}
    with jobs.batches.admit(record,scope(directory,space),batch['id'],batch['revision']) as ref:
        root=jobs.root/'build-one';job=json.loads((root/'job.json').read_bytes())
        job.update(input_id=record['id'],input_binding=binding,batch_ref=ref)
        (root/'job.json').write_text(json.dumps(job),encoding='utf-8')
        path=root/'output/model.json';model=json.loads(path.read_bytes())
        model['source']={'input_binding':binding,'batch_ref':ref,
                         'snapshot_sha256':binding['snapshot_sha256'],'tracking_sha256':binding['tracking_sha256']}
        path.write_text(json.dumps(model),encoding='utf-8')
    return jobs,spaces,uploaded,batch


def test_uploaded_receipt_and_batch_survive_publication_and_consumer_restart(tmp_path):
    jobs,spaces,uploaded,batch=bound_fixture(tmp_path);space=spaces[0]['id']
    selection=jobs.select('build-one',0,space);pubs=PreviewPublications(jobs)
    published=pubs.publish('build-one',selection['revision'],space);record,model=pubs.read(published['id'])
    raw=export_bundle(record,model);offline=OfflinePreview(raw,published['id'],sha(raw))
    source=offline.manifest['source'];receipt=source['input_binding']['registration_ref']
    assert receipt['method']=='uploaded_package' and receipt['package_sha256']==uploaded['upload']['sha256']
    assert source['batch_ref']['batch_id']==batch['id'] and source['batch_ref']['admitted_revision']==2
    assert source['batch_ref']['sealed_members_sha256']==batch['sealed_members_sha256']
    report=batch_results(jobs.batches,jobs,pubs,batch['id'],space)
    assert report['attempts'][0]['id']=='build-one' and report['publications'][0]['id']==published['id']
    bundle=tmp_path/'offline.zip';bundle.write_bytes(raw)
    consumer=PersistentPreviewConsumer.initialize(tmp_path/'consumer',space)
    consumer.install(bundle,published['id'],sha(raw));assert consumer.status()['saved_reference'] is None
    session=consumer.activate(published['id'],sha(raw),0);point=[-.05,.05,.05]
    assert session.query(point)['state']=='surface_candidate'
    bundle.unlink();reopened=PersistentPreviewConsumer(tmp_path/'consumer')
    assert reopened.status()['restore_required']
    restored=reopened.restore(published['id'],sha(raw),1)
    assert restored.query(point)==session.query(point)


def test_batch_does_not_retroactively_claim_unbound_candidates(tmp_path):
    jobs,spaces,uploaded,batch=bound_fixture(tmp_path);root=jobs.root/'build-one'
    for path,key in [(root/'job.json','batch_ref'),(root/'output/model.json','source')]:
        doc=json.loads(path.read_bytes())
        if key=='source':doc[key].pop('batch_ref')
        else:doc.pop(key)
        path.write_text(json.dumps(doc),encoding='utf-8')
    report=batch_results(jobs.batches,jobs,PreviewPublications(jobs),batch['id'],spaces[0]['id'])
    assert report['attempts']==report['publications']==[]
    assert jobs.model('build-one').manifest['source']['input_binding']['id']==uploaded['input']['id']


def test_foreign_batch_and_mixed_candidate_source_are_rejected(tmp_path):
    jobs,spaces,_,batch=bound_fixture(tmp_path)
    with pytest.raises(ValueError,match='space_ownership_mismatch'):
        jobs.batches.read(batch['id'],spaces[1]['id'])
    path=jobs.root/'build-one/output/model.json';doc=json.loads(path.read_bytes())
    doc['source']['input_binding']['registration_ref']['package_sha256']='0'*64
    path.write_text(json.dumps(doc),encoding='utf-8')
    with pytest.raises(ValueError,match='candidate_input_binding_mismatch'):
        jobs.select('build-one',0,spaces[0]['id'])
    assert jobs.selection(spaces[0]['id'])['revision']==0


def test_lineage_exposes_fixed_upload_receipt_and_batch_without_rewriting_snapshot(tmp_path):
    from packages.service.preview_lineage import lineage
    jobs,spaces,uploaded,batch=bound_fixture(tmp_path);space=spaces[0]['id']
    jobs.select('build-one',0,space);pubs=PreviewPublications(jobs);record=pubs.publish('build-one',1,space)
    path=pubs.root/record['id']/'model.json';before=path.read_bytes()
    report=lineage(pubs,record['id']);node=report['nodes'][0]
    assert node['status']=='matched' and node['registration_ref']['package_sha256']==uploaded['upload']['sha256']
    assert node['batch_ref']['batch_id']==batch['id'] and node['batch_ref']['admitted_revision']==2
    assert report['nodes'][1]['status']=='matched' and path.read_bytes()==before
    job_path=jobs.root/'build-one/job.json';job=json.loads(job_path.read_bytes())
    job['batch_ref']['admitted_revision']=1;job_path.write_text(json.dumps(job),encoding='utf-8')
    changed=lineage(pubs,record['id'])
    assert changed['nodes'][1]['status']=='mismatch'
    assert changed['nodes'][0]['batch_ref']['admitted_revision']==2 and path.read_bytes()==before
