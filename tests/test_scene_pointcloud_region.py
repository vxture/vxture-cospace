import json
import numpy as np
import pytest

from packages.data.scene_pointcloud_intake import intake, digest, local_xyz
from packages.data.scene_pointcloud_region import SceneRegions, RegionBudgetExceeded
from packages.data.preview_pointcloud import read_cloud
from test_scene_pointcloud_intake import fixture, opener_at


def scene_at(tmp_path):
    one=fixture(tmp_path)
    two=fixture(tmp_path,'two.laz')
    two[1]['red']=65535
    root=tmp_path/'scene'
    intake([one[0],two[0]],root,scene_name='station',unit_basis='assumed_metre_for_flow_validation',
           chunk_points=3,opener=opener_at({'one.laz':one,'two.laz':two}))
    return SceneRegions(root,digest(root/'scene.json')),one,two


def test_half_open_region_matches_brute_force_and_skips_distant_shards(tmp_path):
    store,one,two=scene_at(tmp_path)
    result=store.read(['one.laz'],[[0.,0.,0.],[2.,5.,5.]],limit=10)
    assert result['matched_points']==result['retained_points']==2
    assert result['source_ordinals'].tolist()==[[0,0],[0,1]]
    expected=local_xyz(one[1],store.scene['sources'][0],store.scene['origin'])[:2]
    np.testing.assert_array_equal(result['points'],expected)
    assert result['shards_skipped']>0


def test_voxel_representative_uses_explicit_source_priority_and_lowest_ordinal(tmp_path):
    store,one,two=scene_at(tmp_path)
    bounds=[[-1.,-1.,-1.],[100.,100.,100.]]
    result=store.read(['two.laz','one.laz'],bounds,voxel_size=100.,limit=10)
    assert result['matched_points']==14 and result['retained_points']==1
    assert result['source_ordinals'].tolist()==[[0,0]]
    assert result['colors'].tolist()==[[255,0,0]]
    # Reordering the physical shard list cannot change the representative.
    for source in store.scene['sources']:source['shards'].reverse()
    repeat=store.read(['two.laz','one.laz'],bounds,voxel_size=100.,limit=10)
    np.testing.assert_array_equal(result['points'],repeat['points'])
    np.testing.assert_array_equal(result['source_ordinals'],repeat['source_ordinals'])


@pytest.mark.parametrize('voxel',[0.,.01])
def test_budget_exceeded_has_no_partial_success_or_output(tmp_path,voxel):
    store,_,_=scene_at(tmp_path)
    with pytest.raises(RegionBudgetExceeded):
        store.prepare(tmp_path/'output',['one.laz'],[[-1.,-1.,-1.],[100.,100.,100.]],limit=1,voxel_size=voxel)
    assert not (tmp_path/'output').exists()


@pytest.mark.parametrize('names,bounds,voxel',[
    ([],[[0,0,0],[1,1,1]],0),(['no.laz'],[[0,0,0],[1,1,1]],0),
    (['one.laz','one.laz'],[[0,0,0],[1,1,1]],0),
    (['one.laz'],[[0,0,0],[0,1,1]],0),(['one.laz'],[[0,0,0],[1,1,float('inf')]],0),
    (['one.laz'],[[0,0,0],[1,1,1]],1e-20),
    (['one.laz'],[[500,500,500],[501,501,501]],0),
])
def test_invalid_or_empty_requests_rejected(tmp_path,names,bounds,voxel):
    store,_,_=scene_at(tmp_path)
    with pytest.raises(ValueError):store.read(names,bounds,voxel_size=voxel)


def test_tampered_intersecting_shard_and_changed_manifest_rejected(tmp_path):
    store,_,_=scene_at(tmp_path)
    shard=store.root/store.scene['sources'][0]['shards'][0]['path'];shard.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='integrity'):
        store.read(['one.laz'],[[-1,-1,-1],[100,100,100]])
    path=store.root/'scene.json';path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='manifest_changed'):
        store.read(['one.laz'],[[-1,-1,-1],[100,100,100]])


def composed_at(tmp_path):
    store,_,_=scene_at(tmp_path)
    report=store.prepare(tmp_path/'composed',['one.laz','two.laz'],[[-1.,-1.,-1.],[100.,100.,100.]],voxel_size=1.)
    return tmp_path/'composed/snapshot',report


def test_portable_composition_receipt_and_full_build_publish_offline(tmp_path):
    from experiments.scripts.pack_input_upload import pack
    from packages.data.input_uploads import InputUploads
    from packages.data.preview_inputs import PreviewInputs
    from packages.lifecycle.preview_spaces import PreviewSpaces
    from packages.construction.preview_jobs import PreviewJobs
    from packages.service.preview_publications import PreviewPublications
    from packages.views.agent.preview_offline import OfflinePreview,export_bundle,sha
    from test_preview_pointcloud import wait_job
    snapshot,report=composed_at(tmp_path)
    checked,points,colors,doc=read_cloud(snapshot)
    assert checked['point_count']==7 and report['matched_points']==14
    bundle=tmp_path/'input.zip';pack(snapshot,None,bundle,'ply_pointcloud')
    directory=PreviewSpaces(tmp_path/'runtime/directory');project=directory.create('project','p')
    scene=directory.create('space','s',project['id']);catalog=PreviewInputs(tmp_path/'runtime/inputs',directory)
    uploaded=InputUploads(catalog).register(bundle,scene['id'],'combined ROI','actor')
    from packages.data.input_facts import facts
    evidence=facts(catalog,uploaded['input']['id'],scene['id'])
    assert evidence['fields']['composition_sources']['value']==['one.laz','two.laz']
    assert evidence['fields']['matched_points']['value']==14
    assert evidence['fields']['retained_points']['value']==7 and not evidence['payload_checked']
    jobs=PreviewJobs(tmp_path/'runtime/jobs',tmp_path,tmp_path,catalog)
    job=jobs.start(uploaded['input']['id'],scene['id']);assert wait_job(jobs,job['id'])['state']=='succeeded'
    jobs.select(job['id'],0,scene['id']);pubs=PreviewPublications(jobs)
    pub=pubs.publish(job['id'],1,scene['id']);record,model=pubs.read(pub['id'])
    raw=export_bundle(record,model);offline=OfflinePreview(raw,pub['id'],sha(raw))
    receipt=offline.manifest['source']['composition']
    assert [s['name'] for s in receipt['sources']]==['one.laz','two.laz']
    assert receipt['matched_points']==14 and receipt['retained_points']==7
    assert not receipt['alignment_verified'] and receipt['unit_basis']=='assumed_metre_for_flow_validation'
    assert receipt['scene_manifest_sha256']==report['scene_manifest_sha256']
    point=(np.floor(points[0].astype(float)/.1)+.5)*.1
    assert offline.query(point)['state']=='surface_candidate'


@pytest.mark.parametrize('problem',['hash','counts','cloud','names','duplicate','bounds','method','path','missing'])
def test_composition_mutations_refuse_intake_even_when_digest_is_rewritten(tmp_path,problem):
    from packages.data.pointcloud_composition import source_set_digest
    snapshot,_=composed_at(tmp_path)
    path=snapshot/'composition.json';receipt=json.loads(path.read_bytes())
    doc_path=snapshot/'pointcloud.json';doc=json.loads(doc_path.read_bytes())
    if problem=='counts':receipt['matched_points']+=1
    if problem=='cloud':receipt['cloud']['points']+=1
    if problem=='names':receipt['sources'][0]['name']='../secret.laz'
    if problem=='duplicate':receipt['sources'][1]['name']=receipt['sources'][0]['name']
    if problem=='bounds':receipt['bounds_local'][0]=receipt['bounds_local'][1]
    if problem=='method':receipt['selection_method']='all_points'
    if problem=='hash':receipt['retained_points']+=1
    path.write_text(json.dumps(receipt),encoding='utf-8')
    if problem=='path':doc['composition_path']='../composition.json'
    elif problem=='missing':path.unlink()
    else:
        doc['provenance']['source_manifest_sha256']=digest(path)
        doc['provenance']['source_member_sha256']=source_set_digest(receipt['sources'])
    doc_path.write_text(json.dumps(doc),encoding='utf-8')
    with pytest.raises((ValueError,OSError)):read_cloud(snapshot)


def test_composition_schema_matches_runtime():
    from pathlib import Path
    from packages.data.pointcloud_composition import Composition
    schema=json.loads(Path('contracts/schemas/pointcloud-composition-v0.1.schema.json').read_bytes())
    assert {k:v for k,v in schema.items() if k!='$schema'}==Composition.model_json_schema()


def test_direct_composition_reader_rejects_paths_before_reading(tmp_path):
    from packages.data.pointcloud_composition import read_composition
    for path in ('../secret.json','/etc/passwd','C:\\private\\secret.json','other.json'):
        with pytest.raises(ValueError,match='composition_path_invalid'):
            read_composition(tmp_path,{'composition_path':path})
    outside=tmp_path.parent/(tmp_path.name+'-outside.json');outside.write_text('{}')
    try:(tmp_path/'composition.json').symlink_to(outside)
    except OSError:pytest.skip('symlink creation unavailable')
    with pytest.raises(ValueError,match='composition_path_invalid'):
        read_composition(tmp_path,{'composition_path':'composition.json'})


@pytest.mark.parametrize('case',['missing','undeclared','foreign_format'])
def test_composition_zip_members_require_matching_declaration(tmp_path,case):
    import zipfile
    from experiments.scripts.pack_input_upload import pack
    from packages.data.input_uploads import InputUploads,UploadRejected
    from test_pointcloud_preparation import catalog_at
    snapshot,_=composed_at(tmp_path)
    original=tmp_path/'input.zip';pack(snapshot,None,original,'ply_pointcloud')
    bundle=tmp_path/'bad.zip'
    with zipfile.ZipFile(original) as src,zipfile.ZipFile(bundle,'w') as dst:
        for name in src.namelist():
            raw=src.read(name)
            if case=='missing' and name=='snapshot/composition.json':continue
            if case=='undeclared' and name=='snapshot/pointcloud.json':
                doc=json.loads(raw);doc.pop('composition_path');raw=json.dumps(doc).encode()
            if case=='foreign_format' and name=='input.json':
                raw=b'{"profile":"cospace.input-upload/0.1","format":"ros1_lidar_single_frame"}'
            dst.writestr(name,raw)
    catalog,spaces=catalog_at(tmp_path)
    with pytest.raises(UploadRejected):InputUploads(catalog).register(bundle,spaces[0],'bad','actor')
    assert not catalog.list()


def test_composition_tamper_after_registration_refuses_facts_and_resolution(tmp_path):
    from pathlib import Path
    from experiments.scripts.pack_input_upload import pack
    from packages.data.input_uploads import InputUploads,UploadRejected
    from packages.data.input_facts import facts,FactsUnavailable
    from packages.data.preview_preflight import preflight
    from test_pointcloud_preparation import catalog_at
    snapshot,_=composed_at(tmp_path)
    bundle=tmp_path/'input.zip';pack(snapshot,None,bundle,'ply_pointcloud')
    catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    uploaded=store.register(bundle,spaces[0],'combined','actor');identity=uploaded['input']['id']
    record=catalog.read(identity)
    (Path(record['snapshot'])/'composition.json').write_bytes(b'changed')
    assert preflight(catalog,identity)['status']=='failed'
    with pytest.raises(FactsUnavailable):facts(catalog,identity,spaces[0])
    with pytest.raises(ValueError):catalog.resolve(identity)
    with pytest.raises(UploadRejected):store.register(bundle,spaces[0],'repeat','actor')
