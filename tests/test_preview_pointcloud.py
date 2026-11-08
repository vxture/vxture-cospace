import json
from pathlib import Path
import time
import numpy as np
import pytest
from fastapi.testclient import TestClient
from packages.data.preview_pointcloud import read_cloud,FORMAT
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_preflight import preflight
from packages.data.input_facts import facts
from packages.data.input_uploads import InputUploads,UploadRejected
from packages.data.preview_source_config import load_sources
from packages.construction.preview_jobs import PreviewJobs
from packages.construction.preview_model import digest
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.views.agent.preview_offline import OfflinePreview,sha
from experiments.scripts.pack_input_upload import pack
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_real_model_preview import make_preview


def specimen(tmp_path,rgb=False):
    root=tmp_path/'pointcloud';root.mkdir()
    dtype=[(n,'<f4') for n in ('x','y','z')]+([(n,'u1') for n in ('red','green','blue')] if rgb else [])
    array=np.array([(1.,2.,.5,10,20,30),(2.,3.,.6,40,50,60)] if rgb else [(1.,2.,.5),(2.,3.,.6)],dtype=dtype)
    header=('ply\nformat binary_little_endian 1.0\ncomment declared coordinates\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\n'+('property uchar red\nproperty uchar green\nproperty uchar blue\n' if rgb else '')+'end_header\n').encode()
    path=root/'cloud.ply';path.write_bytes(header+array.tobytes())
    doc={'profile':'cospace.pointcloud-input/0.1','cloud':{'path':'cloud.ply','bytes':path.stat().st_size,'sha256':digest(path),'points':2},
        'coordinates':{'unit':'m','frame_id':'sensor/local','axes':['sensor_x','sensor_y','sensor_z'],'scope':'sensor_local','scene_alignment':'unverified'},
        'provenance':{'kind':'derived_single_frame','source_manifest_sha256':'a'*64,'source_member_sha256':'b'*64,'description':'test declaration'}}
    (root/'pointcloud.json').write_text(json.dumps(doc),encoding='utf-8')
    return root


def update(root,change):
    path=root/'pointcloud.json';doc=json.loads(path.read_bytes());change(doc);path.write_text(json.dumps(doc),encoding='utf-8')


@pytest.mark.parametrize('rgb',[False,True])
def test_points_colors_and_explicit_coordinates_preserved(tmp_path,rgb):
    root=specimen(tmp_path,rgb);checked,points,colors,doc=read_cloud(root)
    np.testing.assert_array_equal(points,np.array([[1,2,.5],[2,3,.6]],dtype=np.float32))
    assert colors.tolist()==([[10,20,30],[40,50,60]] if rgb else [[160]*3]*2)
    assert checked['appearance']==('source_rgb' if rgb else 'neutral_not_rgb')
    assert checked['scope']=='sensor_local'
    assert checked['scene_alignment']=='unverified'


@pytest.mark.parametrize('change',[
    lambda d:d['coordinates'].pop('unit'),lambda d:d['coordinates'].update(unit='mm'),
    lambda d:d['coordinates'].update(frame_id=''),lambda d:d['coordinates'].update(scope='global'),
    lambda d:d['coordinates'].update(scene_alignment='verified'),lambda d:d['coordinates'].update(axes=['x','x','z']),
    lambda d:d['cloud'].update(path='../cloud.ply'),lambda d:d['cloud'].update(points=1_000_001),
    lambda d:d['cloud'].update(points=True),lambda d:d['cloud'].update(bytes=0),
    lambda d:d['provenance'].update(source_manifest_sha256='unknown'),lambda d:d.update(unexpected=1)])
def test_missing_or_ambiguous_declarations_rejected(tmp_path,change):
    root=specimen(tmp_path);update(root,change)
    with pytest.raises(ValueError):read_cloud(root)


@pytest.mark.parametrize('mutation',[
    lambda b:b[:-1],lambda b:b+b'\0',lambda b:b.replace(b'format binary_little_endian',b'format binary_big_endian'),
    lambda b:b.replace(b'end_header\n',b'element face 0\nend_header\n'),
    lambda b:b.replace(b'end_header\n',b'property float intensity\nend_header\n'),
    lambda b:b[:b.index(b'end_header\n')+11]+np.array([np.nan,2,.5,2,3,.6],dtype='<f4').tobytes(),
    lambda b:b[:b.index(b'end_header\n')+11]+np.array([1e7,2,.5,2,3,.6],dtype='<f4').tobytes(),
    lambda b:b'x'*8193])
def test_truncated_extra_nonfinite_and_unsupported_layouts_rejected(tmp_path,mutation):
    root=specimen(tmp_path);path=root/'cloud.ply';path.write_bytes(mutation(path.read_bytes()))
    update(root,lambda d:d['cloud'].update(bytes=path.stat().st_size,sha256=digest(path)))
    with pytest.raises(ValueError):read_cloud(root)


def test_integrity_registration_preflight_and_manifest_only_facts(tmp_path):
    root=specimen(tmp_path);directory=PreviewSpaces(tmp_path/'directory');project=directory.create('project','test')
    scene=directory.create('space','scene',project['id']);catalog=PreviewInputs(tmp_path/'catalog',directory)
    record=catalog.register('product',root,space_id=scene['id'],format=FORMAT)
    assert preflight(catalog,record['id'])['counts']=={'point_count':2,'cloud_bytes':record['cloud_bytes']}
    result=facts(catalog,record['id'],scene['id'])
    assert result['fields']['axes']['value']==['sensor_x','sensor_y','sensor_z']
    assert result['fields']['utc_sync']['status']=='unknown'
    assert not result['payload_checked']
    with pytest.raises(ValueError,match='tracking_not_supported'):catalog.register('bad',root,root/'x',scene['id'],FORMAT)
    (root/'cloud.ply').write_bytes(b'changed')
    assert preflight(catalog,record['id'])['status']=='failed'
    assert facts(catalog,record['id'],scene['id'])['payload_checked'] is False
    with pytest.raises(ValueError,match='integrity'):catalog.resolve(record['id'])
    update(root,lambda d:d['coordinates'].update(frame_id='changed'))
    from packages.data.input_facts import FactsUnavailable
    with pytest.raises(FactsUnavailable):facts(catalog,record['id'],scene['id'])


def test_config_pack_upload_dedup_and_reject_missing_coordinates(tmp_path):
    root=specimen(tmp_path);cfg=tmp_path/'sources.json'
    cfg.write_text(json.dumps({'profile':'cospace.preview-sources/0.1','sources':[{'id':'ply','label':'product','enabled':True,'format':FORMAT,'snapshot':'pointcloud'}]}))
    sources,report=load_sources(cfg,tmp_path,True);assert report['enabled_count']==1
    directory=PreviewSpaces(tmp_path/'directory');project=directory.create('project','p');scene=directory.create('space','s',project['id'])
    catalog=PreviewInputs(tmp_path/'catalog',directory);bundle=tmp_path/'ply.zip';pack(root,None,bundle,FORMAT)
    original={p.name:p.read_bytes() for p in root.iterdir()}
    store=InputUploads(catalog);one=store.register(bundle,scene['id'],'existing','manager');two=store.register(bundle,scene['id'],'renamed','manager')
    assert one['created']
    assert not two['created']
    assert one['input']==two['input']
    assert all((root/name).read_bytes()==value for name,value in original.items())
    import zipfile
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bundle) as src,zipfile.ZipFile(bad,'w') as dst:
        for name in src.namelist():
            value=src.read(name)
            if name.endswith('pointcloud.json'):
                doc=json.loads(value);doc['coordinates'].pop('unit');value=json.dumps(doc).encode()
            dst.writestr(name,value)
    with pytest.raises(UploadRejected,match='content_validation_failed'):store.register(bad,scene['id'],'bad','manager')
    assert len(catalog.list())==1


def wait_job(jobs,identity):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        job=next(j for j in jobs.list() if j['id']==identity)
        if job['state'] not in ('queued','running'):return job
        time.sleep(.05)
    raise AssertionError('job timed out')


def test_actual_subprocess_fixed_model_dual_views_publish_lineage_and_offline(tmp_path):
    root=specimen(tmp_path,True);initial=tmp_path/'initial';initial.mkdir();make_preview(initial)
    directory=PreviewSpaces(tmp_path/'directory');project=directory.create('project','p')
    a,b=[directory.create('space',n,project['id']) for n in ('existing scene','other')]
    catalog=PreviewInputs(tmp_path/'catalog',directory);record=catalog.register('existing PLY',root,space_id=a['id'],format=FORMAT)
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path,tmp_path,catalog)
    with TestClient(create_app(initial,jobs,space_directory=directory)) as client:
        assert client.get('/api/inputs/'+record['id']).json()['supported_format'].startswith('PLY')
        assert client.post('/api/builds',json={'input_id':record['id'],'space_id':b['id']}).status_code==409
        created=client.post('/api/builds',json={'input_id':record['id'],'space_id':a['id']});assert created.status_code==202,created.text
        job=wait_job(jobs,created.json()['id']);assert job['state']=='succeeded',(job,(jobs.root/job['id']/'build.log').read_text())
        model=jobs.model(job['id']);m=model.manifest
        admission=job['build_admission']
        assert admission['job_id']==job['id']
        assert admission['source_files_checked'] is True
        assert m['source']['build_admission']==admission
        assert m['human_view']['appearance']=='source_rgb'
        assert m['human_view']['source_model_sha256']==m['agent_view']['source_model_sha256']
        assert m['frame_id']=='sensor/local'
        assert not m['construction']['coordinate_transform_applied']
        with np.load(model.root/'spatial.npz') as arrays:np.testing.assert_array_equal(arrays['points'],read_cloud(root)[1])
        stages=jobs.stages(a['id'],job['id']);assert stages['candidate_ready'] and all(v['state']=='succeeded' for v in stages['views'].values())
        rerun=jobs.derive_view(a['id'],job['id'],'human','a'*32)['job'];assert wait_job(jobs,rerun['id'])['state']=='succeeded'
        assert jobs.model(rerun['id']).manifest['derivation']['frozen_model']==m['derivation']['frozen_model']
        assert jobs.model(rerun['id']).manifest['source']['build_admission']==admission
        from packages.ontology.preview_versions import PreviewOntologies
        from packages.spatial.preview_objects import SemanticRequest
        from packages.construction.preview_semantics import annotate
        rules=PreviewOntologies(tmp_path/'rules');rule=rules.register('configs/ontology/indoor-equipment-v0.1.json')
        annotated=annotate(jobs,rules,SemanticRequest(space_id=a['id'],base_candidate_id=job['id'],
            base_manifest_sha256=digest(model.root/'model.json'),
            ontology_ref={k:rule[k] for k in ('ontology_id','version','sha256')},
            objects=[{'object_id':'cabinet-01','type_id':'cabinet','properties':{'name':'test'},'point_index':0}]))
        assert annotated['build_admission']==admission
        assert jobs.model(annotated['id']).manifest['source']['build_admission']==admission
        assert jobs.selection(a['id'])['revision']==0
        assert client.post('/api/selection',json={'space_id':a['id'],'candidate_id':job['id'],'expected_revision':0}).status_code==200
        pub_response=client.post('/api/publications',json={'space_id':a['id'],'candidate_id':job['id'],'expected_revision':1});assert pub_response.status_code==201,pub_response.text
        pub=pub_response.json();raw=client.get(pub['preview_url']+'offline.zip').content
        from packages.data.preflight_records import PreflightRecords
        checks=PreflightRecords(catalog)
        checks.save(record['id'],preflight(catalog,record['id']),'test',checks.fingerprint(record['id']))
        provenance=client.get(pub['preview_url']+'api/provenance').json()
        assert provenance['build_admission_status']=='recorded'
        assert provenance['build_admission']==admission
        assert admission['saved_preflight_sequence'] is None
        offline=OfflinePreview(raw,pub['id'],sha(raw));point=[1.05,2.05,.55]
        assert client.post(pub['query_url'],json={'point_m':point}).json()==offline.query(point)
        assert offline.query(point)['state']=='surface_candidate'
        assert offline.query([100,100,100])['state']=='unknown'
        assert all(n['status']=='matched' for n in client.get(pub['preview_url']+'api/lineage').json()['nodes'])
        from packages.data.preview_artifacts import artifact_catalog
        from packages.service.preview_publications import PreviewPublications
        artifact=artifact_catalog(PreviewPublications(jobs),a['id'])
        assert next(i for i in artifact['items'] if i['key']=='input:'+record['id'])['integrity']=='record_only'
        assert all(r['status']=='matched' for r in artifact['relations'])
        assert client.get('/api/publications',params={'space_id':b['id']}).json()['publications']==[]
        assert m['robot_ready'] is False
        assert m['quality']['grade']=='unverified'


def test_failed_pointcloud_worker_retry_preserves_original_and_is_repeat_safe(tmp_path,monkeypatch):
    root=specimen(tmp_path);directory=PreviewSpaces(tmp_path/'directory');project=directory.create('project','p')
    scene=directory.create('space','s',project['id']);catalog=PreviewInputs(tmp_path/'catalog',directory)
    entry=catalog.register('product',root,space_id=scene['id'],format=FORMAT)
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path,tmp_path,catalog)
    class Failed:
        def poll(self):return 1
    with monkeypatch.context() as patch:
        patch.setattr('packages.construction.preview_jobs.subprocess.Popen',lambda *a,**k:Failed())
        first=jobs.start(entry['id'],scene['id']);assert wait_job(jobs,first['id'])['state']=='failed'
    original=(jobs.root/first['id']/'job.json').read_bytes()
    result=jobs.retry(scene['id'],first['id'],'c'*32)
    assert result['job']['build_admission']['job_id']==result['job']['id']
    assert result['job']['build_admission']['sha256']!=first['build_admission']['sha256']
    assert wait_job(jobs,result['job']['id'])['state']=='succeeded'
    assert not jobs.retry(scene['id'],first['id'],'c'*32)['created']
    assert (jobs.root/first['id']/'job.json').read_bytes()==original
    assert jobs.selection(scene['id'])['revision']==0


def test_admission_save_failure_never_starts_worker_and_tampering_rejected(tmp_path,monkeypatch):
    from packages.construction.build_admission import receipt,validate
    root=specimen(tmp_path);catalog=PreviewInputs(tmp_path/'catalog')
    entry=catalog.register('product',root,format=FORMAT)
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path,tmp_path,catalog)
    monkeypatch.setattr(jobs,'save',lambda *a:(_ for _ in ()).throw(OSError('disk full')))
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',lambda *a,**k:pytest.fail('must not launch'))
    with pytest.raises(OSError,match='disk full'):jobs.start(entry['id'])
    binding={k:v for k,v in entry.items() if k not in ('snapshot','tracking')}
    value=receipt('build-test',binding)
    with pytest.raises(ValueError,match='build_admission_invalid'):validate(value|{'job_id':'build-changed'},binding)
    with pytest.raises(ValueError,match='build_admission_invalid'):validate(value,binding|{'label':'changed'})


def test_admission_survives_failed_spawn_and_restart_without_success_claim(tmp_path,monkeypatch):
    root=specimen(tmp_path);catalog=PreviewInputs(tmp_path/'catalog')
    entry=catalog.register('product',root,format=FORMAT)
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path,tmp_path,catalog)
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',lambda *a,**k:(_ for _ in ()).throw(OSError('spawn failed')))
    failed=jobs.start(entry['id']);assert failed['state']=='failed'
    admission=failed['build_admission']
    failed['state']='running';jobs.save(failed)
    restarted=PreviewJobs(jobs.root,tmp_path,tmp_path,catalog)
    saved=restarted.list()[0]
    assert saved['state']=='interrupted'
    assert saved['build_admission']==admission


def test_source_changed_after_admission_fails_worker(tmp_path,monkeypatch):
    root=specimen(tmp_path);catalog=PreviewInputs(tmp_path/'catalog')
    entry=catalog.register('product',root,format=FORMAT)
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path,tmp_path,catalog)
    from packages.construction.preview_jobs import subprocess
    spawn=subprocess.Popen
    def changed(*args,**kwargs):
        (root/'cloud.ply').write_bytes(b'changed after admission')
        return spawn(*args,**kwargs)
    monkeypatch.setattr(subprocess,'Popen',changed)
    started=jobs.start(entry['id']);finished=wait_job(jobs,started['id'])
    assert finished['state']=='failed'
    assert finished['build_admission']==started['build_admission']
    assert not (jobs.root/started['id']/'output').exists()


def test_published_schema_and_prepare_tool_match_runtime_and_leave_source_untouched(tmp_path):
    from packages.data.preview_pointcloud import Manifest
    from experiments.scripts.prepare_pointcloud_input import prepare
    from jsonschema import Draft202012Validator
    root=specimen(tmp_path);doc=json.loads((root/'pointcloud.json').read_bytes())
    schema=json.loads(Path('contracts/schemas/pointcloud-input-v0.1.schema.json').read_bytes())
    assert {k:v for k,v in schema.items() if k!='$schema'}==Manifest.model_json_schema()
    Draft202012Validator(schema).validate(doc)
    before={p.name:p.read_bytes() for p in root.iterdir()}
    summary=prepare(root/'cloud.ply',tmp_path/'prepared',points=2,frame_id='sensor/local',axes=['sensor_x','sensor_y','sensor_z'],
        scope='sensor_local',source_manifest=root/'pointcloud.json',source_member_sha256='b'*64,description='declared source',kind='derived_single_frame')
    assert summary['point_count']==2
    assert summary['source_unchanged']
    assert all((root/name).read_bytes()==value for name,value in before.items())


def test_manifest_duplicate_keys_and_size_budget(tmp_path):
    root=specimen(tmp_path);path=root/'pointcloud.json';original=path.read_text()
    path.write_text(original.replace('"profile":','"profile":"duplicate","profile":'))
    with pytest.raises(ValueError,match='declaration_invalid'):read_cloud(root)
    path.write_bytes(b' '*64_001)
    with pytest.raises(ValueError,match='manifest_budget'):read_cloud(root)
