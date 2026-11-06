import json
from pathlib import Path
import pytest
from packages.data.preflight_records import PreflightRecords,PreflightUnavailable
from packages.data.preview_preflight import preflight
from packages.service.space_preparation import preparation
from test_space_sources import sources_secured
from test_platform_business import secured,sign_in
from test_platform_login import runtime


def test_history_persists_and_input_changes_do_not_borrow_old_pass(sources_secured):
    secured,sources,input=sources_secured;_,_,_,_,jobs,_,spaces,*_=secured
    store=PreflightRecords(jobs.inputs);identity=input['id'];space=spaces[0]['id']
    assert store.latest(identity) is None and not store.path.exists()
    fingerprint=store.fingerprint(identity);report=preflight(jobs.inputs,identity)
    saved=store.save(identity,report,'usr_engineer',fingerprint)
    assert saved['sequence']==1 and saved['status']=='passed'
    latest=PreflightRecords(jobs.inputs).latest(identity)
    assert latest['registration_matches'] and not latest['current_files_checked']
    p=jobs.inputs.root/(identity+'.json');record=json.loads(p.read_bytes());record['label']='Updated record';p.write_text(json.dumps(record))
    assert not store.latest(identity)['registration_matches']
    with pytest.raises(ValueError):store.save(identity,report,'usr_engineer',fingerprint)
    assert preparation(jobs,sources,space,identity)['inputs'][0]['check_status']=='registration_changed'


def test_failed_check_supersedes_old_pass_and_summary_does_no_file_io(sources_secured,monkeypatch):
    secured,sources,input=sources_secured;_,_,_,_,jobs,_,spaces,*_=secured
    identity=input['id'];space=spaces[0]['id'];store=PreflightRecords(jobs.inputs)
    report=preflight(jobs.inputs,identity);store.save(identity,report,'usr_engineer',store.fingerprint(identity))
    (Path(input['snapshot'])/'raw/d.pgm').write_bytes(b'changed')
    failed=preflight(jobs.inputs,identity);assert failed['status']=='failed'
    store.save(identity,failed,'usr_engineer',store.fingerprint(identity))
    monkeypatch.setattr(jobs.inputs,'resolve',lambda *a:pytest.fail('summary must not check source files'))
    monkeypatch.setattr(jobs,'poll',lambda *a:pytest.fail('summary must not poll'))
    result=preparation(jobs,sources,space,identity)
    assert result['inputs'][0]['check_status']=='failed'
    assert result['next_action']['module']=='data'
    assert result['inputs'][0]['check_sequence']==2


def test_authorized_check_save_reload_and_workflow_follow_input(sources_secured):
    secured,sources,input=sources_secured;_,c,_,_,jobs,_,spaces,*_=secured
    headers,_=sign_in(secured,'usr_engineer');identity=input['id'];space=spaces[0]['id']
    path='/api/inputs/'+identity+'/preflight'
    assert c.get(path).json()['last_check'] is None
    assert c.post(path).status_code==403
    r=c.post(path,headers=headers);assert r.status_code==200,r.text
    assert r.json()['actor']=='usr_engineer' and r.json()['sequence']==1
    assert c.get(path).json()['last_check']['registration_matches']
    result=c.get('/api/workflow',params={'space_id':space,'input_id':identity})
    assert result.status_code==200,result.text
    data=result.json();prep=data['preparation']
    assert prep['selected_input_id']==identity and prep['next_action']['module']=='build'
    assert prep['next_action']['values']['input']==identity and prep['next_action']['allowed']
    assert data['candidate_ref'] and data['publication_ref']
    assert not data['source_files_rechecked'] and not data['jobs_polled']
    # Source configuration is empty; it must not invalidate an existing registration.
    assert prep['enabled_source_count']==0
    assert c.get('/api/workflow',params={'space_id':space}).json()['preparation']['next_action']['label']=='选择资料并预检'


def test_viewer_cannot_read_checks_and_workflow_hides_preparation(sources_secured,monkeypatch):
    secured,sources,input=sources_secured;_,c,_,_,jobs,_,spaces,*_=secured;headers,_=sign_in(secured)
    monkeypatch.setattr(PreflightRecords,'latest',lambda *a:pytest.fail('authorize before saved check reads'))
    assert c.get('/api/inputs/'+input['id']+'/preflight').status_code==403
    assert c.post('/api/inputs/'+input['id']+'/preflight',headers=headers).status_code==403
    data=c.get('/api/workflow',params={'space_id':spaces[0]['id']}).json()
    assert 'preparation' not in data
    assert not next(s for s in data['stages'] if s['id']=='data')['action']['allowed']
    assert c.get('/api/workflow',params={'space_id':spaces[1]['id']}).status_code==403
    assert c.get('/api/workflow',params={'space_id':spaces[1]['id'],'input_id':input['id']}).status_code==403


def test_store_corruption_fails_closed(sources_secured):
    secured,_,input=sources_secured;_,c,_,_,jobs,_,spaces,*_=secured;sign_in(secured,'usr_engineer')
    store=PreflightRecords(jobs.inputs);store.path.write_bytes(b'broken')
    assert c.get('/api/inputs/'+input['id']+'/preflight').status_code==503
    assert c.get('/api/workflow',params={'space_id':spaces[0]['id']}).status_code==503
    with pytest.raises(PreflightUnavailable):store.latest(input['id'])


def test_preparation_requires_explicit_input_and_lifecycle_is_independent(sources_secured):
    secured,sources,input=sources_secured;_,_,_,_,jobs,_,spaces,*_=secured
    space=spaces[0]['id'];identity=input['id'];store=PreflightRecords(jobs.inputs)
    store.save(identity,preflight(jobs.inputs,identity),'usr_engineer',store.fingerprint(identity))
    from packages.lifecycle.preview_control import ControlChange
    from packages.construction.preview_model import digest
    from packages.service.preview_publications import PreviewPublications
    publications=PreviewPublications(jobs)
    snapshot=jobs.controls.report(publications,space,'input:'+identity)['snapshot_sha256']
    jobs.controls.change(publications,ControlChange(space_id=space,artifact='input:'+identity,expected_revision=0,
        expected_snapshot_sha256=snapshot,operation='disable_input',reason='disable'))
    result=preparation(jobs,sources,space,identity)
    assert result['next_action']['module']=='data' and result['inputs'][0]['lifecycle_state']=='disabled'
    with pytest.raises(PermissionError):preparation(jobs,sources,space,'input-'+'f'*16)


def test_empty_scene_upload_does_not_require_configured_source(sources_secured):
    secured,sources,_=sources_secured;_,_,_,_,jobs,_,spaces,*_=secured
    result=preparation(jobs,sources,spaces[1]['id'])
    assert not result['inputs'] and result['enabled_source_count']==0
    assert result['next_action']['intent']=='import'
    assert result['next_action']['values']['tab']=='inputs'
    assert not result['can_submit']


def test_batch_conditions_are_readonly_and_shared_with_admission(sources_secured,monkeypatch):
    from test_preview_batches import create,change,files
    secured,sources,input=sources_secured;_,_,_,_,jobs,_,spaces,*_=secured
    space=spaces[0]['id'];identity=input['id'];store=PreflightRecords(jobs.inputs)
    store.save(identity,preflight(jobs.inputs,identity),'usr_engineer',store.fingerprint(identity))
    assert preparation(jobs,sources,space,identity)['can_submit']
    batch=create(jobs,space);batch=change(jobs.batches,batch,'replace_members',input_ids=[identity])
    report=preparation(jobs,sources,space,identity)
    assert not report['can_submit'] and report['inputs'][0]['batch']['status']=='blocked'
    assert report['next_action']['values']['tab']=='batches'
    batch=change(jobs.batches,batch,'seal')
    second=create(jobs,space);second=change(jobs.batches,second,'replace_members',input_ids=[identity]);second=change(jobs.batches,second,'seal')
    monkeypatch.setattr(jobs.inputs,'resolve',lambda *a:pytest.fail('summary must not read source payloads'))
    monkeypatch.setattr(jobs,'poll',lambda *a:pytest.fail('summary must not poll workers'))
    before=files(jobs.root.parent)
    report=preparation(jobs,sources,space,identity)
    assert report['inputs'][0]['batch']['status']=='selection_required'
    assert len(report['inputs'][0]['batch']['choices'])==2 and not report['can_submit']
    assert report['next_action']['module']=='build' and 'batch' not in report['next_action']['values']
    explicit=preparation(jobs,sources,space,identity,batch['id'])
    assert explicit['can_submit'] and explicit['selected_batch_id']==batch['id']
    assert explicit['next_action']['values']['batch']==batch['id']
    assert files(jobs.root.parent)==before
    off=change(jobs.batches,batch,'disable')
    assert not preparation(jobs,sources,space,identity,off['id'])['can_submit']
    assert preparation(jobs,sources,space,identity,second['id'])['can_submit']
    from packages.lifecycle.preview_scope import scope
    with pytest.raises(ValueError,match='batch_not_sealed_or_disabled'):
        with jobs.batches.admit(jobs.inputs.read(identity),scope(jobs.directory,space),off['id'],off['revision']):
            pytest.fail('disabled batch must be rejected')


def test_explicit_wrong_batch_is_not_replaced_and_progress_matches(sources_secured):
    from test_preview_batches import create,change,sealed
    secured,sources,input=sources_secured;_,c,_,_,jobs,_,spaces,*_=secured
    headers,_=sign_in(secured,'usr_engineer');space=spaces[0]['id'];identity=input['id']
    assert c.post('/api/inputs/'+identity+'/preflight',headers=headers).status_code==200
    empty=create(jobs,space)
    report=preparation(jobs,sources,space,identity,empty['id'])
    assert not report['can_submit'] and report['selected_batch_id']==empty['id']
    assert report['next_action']['values']['batch']==empty['id']
    foreign=create(jobs,spaces[1]['id'])
    with pytest.raises(ValueError,match='batch_not_in_space'):preparation(jobs,sources,space,identity,foreign['id'])
    result=c.get('/api/workflow',params={'space_id':space,'input_id':identity,'batch_id':empty['id']})
    assert result.status_code==200,result.text
    assert not result.json()['preparation']['can_submit']
    assert result.json()['summary']['work']['label']=='资料待准备'
    assert result.json()['summary']['work']['action']['values']['batch']==empty['id']
    assert c.get('/api/workflow',params={'space_id':space,'input_id':identity,'batch_id':foreign['id']}).status_code==409
    other=jobs.inputs.register('同场景另一份资料',input['snapshot'],input['tracking'],space)
    wrong=sealed(jobs,space,other['id'])
    mismatch=preparation(jobs,sources,space,identity,wrong['id'])
    assert next(row for row in mismatch['inputs'] if row['input_id']==identity)['batch']['issue']=='input_not_in_batch'
    assert '不包含当前资料' in mismatch['detail'] and not mismatch['can_submit']


@pytest.mark.parametrize('case',['missing','failed','changed'])
def test_preparation_explains_checks_before_batch_selection(sources_secured,case):
    secured,sources,input=sources_secured;_,_,_,_,jobs,_,spaces,*_=secured
    identity=input['id'];space=spaces[0]['id'];store=PreflightRecords(jobs.inputs)
    if case!='missing':
        report=preflight(jobs.inputs,identity)
        if case=='failed':report.update(status='failed')
        store.save(identity,report,'usr_engineer',store.fingerprint(identity))
        if case=='changed':
            path=jobs.inputs.root/(identity+'.json');record=json.loads(path.read_bytes());record['label']='changed';path.write_text(json.dumps(record))
    result=preparation(jobs,sources,space,identity)
    assert not result['can_submit'] and result['next_action']['module']=='data'
