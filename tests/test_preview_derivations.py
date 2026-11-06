"""Independent views preserve frozen geometry and immutable candidate compositions."""
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
from pathlib import Path
import threading
import numpy as np
import pytest
from fastapi.testclient import TestClient
from packages.construction.preview_derivations import freeze,derive,PIPELINE
from packages.construction.preview_model import digest,PreviewModel
from packages.service.preview_publications import PreviewPublications
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_batches import prepared


def fixture(tmp_path,monkeypatch,failed=None):
    initial,jobs,directory,spaces,inputs=prepared(tmp_path);space=spaces[0]['id'];entry=inputs[0]
    identity='build-split';root=jobs.root/identity;root.mkdir();frozen=root/'frozen';frozen.mkdir()
    points=np.array([[.05,.05,.05],[.25,.25,.25]],dtype=np.float32);colors=np.array([[10,20,30],[80,90,100]],dtype=np.uint8)
    np.savez_compressed(frozen/'spatial.npz',points=points,colors=colors)
    binding={k:v for k,v in entry.items() if k not in ('snapshot','tracking')}
    ownership={'space_id':space,'project_id':spaces[0]['project_id']}
    meta={'id':identity,'source':{'input_binding':binding},'frame_id':'test_anchor','unit':'m','axes':['right','down','forward'],
        'construction':{'input_frames':1,'used_frames':1,'model_points':2},'bounds_m':[[.05]*3,[.25]*3],
        'data_kind':'real_rgbd_candidate','quality':{'grade':'unverified'},'real_release_ready':False,'robot_ready':False,**ownership}
    freeze_record=freeze(frozen,meta)
    job={'id':identity,'state':'running','stage':'building_model','pipeline':PIPELINE,'created_at':'2026-11-04T00:00:00+00:00',
        'input_id':entry['id'],'input_binding':binding,'method':'rebuild_from_frozen_rgbd_and_existing_poses','candidate_url':None,'error':None,**ownership}
    jobs.save(job);failure={'kind':failed};calls=[]
    class Process:
        def __init__(self,code):self.code=code
        def poll(self):return self.code
    def launch(command,**kwargs):
        assert command[2]=='experiments.scripts.derive_frozen_preview';calls.append(command)
        task=json.loads(Path(command[command.index('--task')+1]).read_bytes())
        if task['view_kind']==failure['kind']:return Process(23)
        derive(Path(command[command.index('--frozen')+1]),Path(command[command.index('--output')+1]),task)
        return Process(0)
    monkeypatch.setattr('packages.construction.preview_derivations.subprocess.Popen',launch)
    jobs.split.begin(job);jobs.list()
    return initial,jobs,directory,spaces,job,failure,calls


@pytest.mark.parametrize('kind',['human','agent'])
def test_failed_view_retries_alone_keeps_model_other_view_and_history(tmp_path,monkeypatch,kind):
    _,jobs,_,spaces,old,failure,calls=fixture(tmp_path,monkeypatch,kind);space=spaces[0]['id']
    record=next(r for r in jobs.list() if r['id']==old['id']);assert record['state']=='views_failed'
    stages=jobs.stages(space,old['id']);assert stages['views'][kind]['state']=='failed' and not stages['candidate_ready']
    other='agent' if kind=='human' else 'human';other_ref=record['view_tasks'][other]
    model=jobs.root/old['id']/'frozen';protected={p.name:p.read_bytes() for p in model.iterdir()}
    old_bytes=(jobs.root/old['id']/'job.json').read_bytes();failure['kind']=None;count=len(calls)
    result=jobs.derive_view(space,old['id'],kind,'a'*32);new=result['job'];jobs.list()
    assert len(calls)==count+1 and new['view_tasks'][other]==other_ref and new['frozen_model']==record['frozen_model']
    current=jobs.model(new['id']);assert current.manifest['derivation']['frozen_model']==record['frozen_model']
    assert current.manifest['derivation']['views'][other]['id']==other_ref['task_id']
    assert (jobs.root/old['id']/'job.json').read_bytes()==old_bytes
    assert all((model/name).read_bytes()==raw for name,raw in protected.items())
    assert (current.root/'spatial.npz').read_bytes()==protected['spatial.npz']
    assert jobs.selection(space)['candidate_id'] is None
    again=jobs.derive_view(space,old['id'],kind,'a'*32);assert not again['created'] and again['job']['id']==new['id']
    with pytest.raises(ValueError,match='conflict'):jobs.derive_view(space,old['id'],other,'a'*32)


def test_rederive_successful_view_creates_new_composition_and_pins_release(tmp_path,monkeypatch):
    _,jobs,_,spaces,old,_,calls=fixture(tmp_path,monkeypatch);space=spaces[0]['id']
    selection=jobs.select(old['id'],0,space);pubs=PreviewPublications(jobs);release=pubs.publish(old['id'],selection['revision'],space)
    before={p.name:p.read_bytes() for p in (jobs.root/old['id']/'output').iterdir()};old_pub={p.name:p.read_bytes() for p in (pubs.root/release['id']).iterdir()}
    new=jobs.derive_view(space,old['id'],'human','b'*32)['job'];jobs.list();model=jobs.model(new['id'])
    assert new['id']!=old['id'] and model.manifest['members']['spatial.npz']['sha256']==release['source_model_sha256']
    assert new['view_tasks']['agent']==old['view_tasks']['agent'] and new['view_tasks']['human']!=old['view_tasks']['human']
    assert all((jobs.root/old['id']/'output'/name).read_bytes()==raw for name,raw in before.items())
    assert all((pubs.root/release['id']/name).read_bytes()==raw for name,raw in old_pub.items())
    assert pubs.read(release['id'])[0]==release and jobs.selection(space)['candidate_id']==old['id']
    with pytest.raises(ValueError,match='selection_changed'):pubs.publish(new['id'],selection['revision'],space)


def test_mixed_models_or_corrupt_views_cannot_compose_or_publish(tmp_path,monkeypatch):
    _,jobs,_,spaces,old,_,_=fixture(tmp_path,monkeypatch);space=spaces[0]['id'];model=jobs.model(old['id'])
    path=model.root/'model.json';manifest=json.loads(path.read_bytes());manifest['derivation']['views']['agent']['frozen_model']['job_id']='build-other'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='composition'):PreviewModel(model.root)
    with pytest.raises(ValueError):jobs.select(old['id'],0,space)
    # Corrupt the successful counterpart: a new combination must not reuse it.
    agent_root,_=jobs.split.manifest(old['view_tasks']['agent'],old['frozen_model'],'agent')
    (agent_root/'agent.npz').write_bytes(b'bad')
    count=len(list(jobs.root.glob('*/job.json')))
    with pytest.raises(ValueError,match='integrity'):jobs.derive_view(space,old['id'],'human','c'*32)
    assert len(list(jobs.root.glob('*/job.json')))==count


def test_frozen_model_tampering_and_cross_scene_rejected_before_launch(tmp_path,monkeypatch):
    _,jobs,_,spaces,old,_,calls=fixture(tmp_path,monkeypatch);count=len(calls)
    with pytest.raises(ValueError,match='ownership'):jobs.derive_view(spaces[1]['id'],old['id'],'human','d'*32)
    (jobs.root/old['id']/'frozen/spatial.npz').write_bytes(b'bad')
    with pytest.raises(ValueError,match='frozen_model_integrity'):jobs.derive_view(spaces[0]['id'],old['id'],'human','d'*32)
    assert len(calls)==count


def test_equal_geometry_different_frozen_versions_cannot_mix_views(tmp_path,monkeypatch):
    _,jobs,_,spaces,old,_,_=fixture(tmp_path,monkeypatch);second=dict(old,id='build-second',state='running',stage='building_model')
    root=jobs.root/second['id'];(root/'frozen').mkdir(parents=True)
    shutil.copyfile(jobs.root/old['id']/'frozen/spatial.npz',root/'frozen/spatial.npz')
    meta=json.loads((jobs.root/old['id']/'frozen/frozen.json').read_bytes())['metadata'];meta['id']=second['id'];freeze(root/'frozen',meta)
    jobs.save(second);jobs.split.begin(second);jobs.list()
    mixed=dict(second,id='build-mixed',state='views_failed',view_tasks={'human':second['view_tasks']['human'],'agent':old['view_tasks']['agent']})
    (jobs.root/mixed['id']).mkdir();jobs.save(mixed)
    assert old['frozen_model']['source_model_sha256']==second['frozen_model']['source_model_sha256']
    with pytest.raises(ValueError,match='view_task_not_ready'):jobs.split.compose(mixed)
    assert not (jobs.root/mixed['id']/'output').exists()
    with pytest.raises(ValueError,match='candidate_not_available'):jobs.select(mixed['id'],0,spaces[0]['id'])


def test_request_deduplicates_concurrently_and_survives_restart(tmp_path,monkeypatch):
    _,jobs,_,spaces,old,_,calls=fixture(tmp_path,monkeypatch);barrier=threading.Barrier(2);count=len(calls)
    def worker():barrier.wait();return jobs.derive_view(spaces[0]['id'],old['id'],'human','e'*32)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:worker(),range(2)))
    assert sorted(r['created'] for r in results)==[False,True] and len({r['job']['id'] for r in results})==1 and len(calls)==count+1
    jobs.list()
    from packages.construction.preview_jobs import PreviewJobs
    restarted=PreviewJobs(jobs.root,jobs.snapshot,jobs.tracking,jobs.inputs)
    assert restarted.derive_view(spaces[0]['id'],old['id'],'human','e'*32)['created'] is False


def test_view_api_explicit_scope_origin_and_parameters(tmp_path,monkeypatch):
    initial,jobs,directory,spaces,old,_,_=fixture(tmp_path,monkeypatch);space=spaces[0]['id']
    with TestClient(create_app(initial,jobs,space_directory=directory)) as client:
        query={'space_id':space,'candidate_id':old['id']};body=query|{'view_kind':'agent','request_id':'f'*32}
        assert client.get('/api/build-stages',params=query).json()['candidate_ready']
        assert client.get('/api/build-stages',params=query|{'space_id':spaces[1]['id']}).status_code==409
        assert client.post('/api/view-derivations',json=body,headers={'Origin':'https://other.invalid'}).status_code==403
        for changes in ({'resolution_m':1},{'view_kind':'other'},{'request_id':'bad'}):assert client.post('/api/view-derivations',json=body|changes).status_code==422
        response=client.post('/api/view-derivations',json=body);assert response.status_code==202,response.text
        replay=client.post('/api/view-derivations',json=body);assert replay.status_code==200
        assert replay.json()['job']['id']==response.json()['job']['id']
        jobs.list()


def test_view_derivation_reads_only_frozen_snapshot_not_sensor_sources(tmp_path,monkeypatch):
    _,jobs,_,spaces,old,_,_=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(jobs.inputs,'resolve',lambda *a:pytest.fail('view rerun must never reprocess raw inputs'))
    source=jobs.inputs.read(old['input_id']);Path(source['snapshot']).rename(tmp_path/'raw_source_unavailable')
    new=jobs.derive_view(spaces[0]['id'],old['id'],'agent','1'*32)['job'];jobs.list()
    assert jobs.model(new['id']).manifest['derivation']['frozen_model']==old['frozen_model']


def test_restart_preserves_model_and_allows_only_interrupted_view_rerun(tmp_path,monkeypatch):
    _,jobs,_,spaces,old,_,_=fixture(tmp_path,monkeypatch)
    path,task=jobs.split.task(old['view_tasks']['agent']);task['state']='running';path.write_text(json.dumps(task))
    record=next(r for r in jobs.list() if r['id']==old['id']);record.update(state='running',stage='deriving_views');jobs.save(record)
    from packages.construction.preview_jobs import PreviewJobs
    restarted=PreviewJobs(jobs.root,jobs.snapshot,jobs.tracking,jobs.inputs)
    stages=restarted.stages(spaces[0]['id'],old['id'])
    assert stages['views']['agent']['state']=='interrupted' and stages['views']['human']['state']=='succeeded'
    new=restarted.derive_view(spaces[0]['id'],old['id'],'agent','2'*32)['job'];restarted.list()
    assert restarted.model(new['id']).manifest['derivation']['frozen_model']==old['frozen_model']
    assert new['view_tasks']['human']==old['view_tasks']['human']


def test_preparation_counts_view_failure_without_source_io_or_poll(tmp_path,monkeypatch):
    _,jobs,directory,spaces,old,_,_=fixture(tmp_path,monkeypatch,'agent')
    from packages.service.space_preparation import preparation
    from packages.data.space_sources import SpaceSources
    monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('preparation must not advance tasks'))
    monkeypatch.setattr(jobs.inputs,'resolve',lambda *a:pytest.fail('preparation must not read raw sources'))
    result=preparation(jobs,SpaceSources(directory.root,{}),spaces[0]['id'],old['input_id'])
    assert result['inputs'][0]['saved_build_counts']['views_failed']==1
