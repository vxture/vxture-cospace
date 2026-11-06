import json
import numpy as np
import pytest
from packages.data.scene_pointcloud_intake import intake, digest
from packages.data.scene_pointcloud_verify import verify
from test_scene_pointcloud_intake import fixture, opener_at


def prepared(tmp_path):
    one=fixture(tmp_path)
    root=tmp_path/'scene'
    intake([one[0]],root,scene_name='s',unit_basis='assumed_metre_for_flow_validation',
           chunk_points=3,opener=opener_at({'one.laz':one}))
    return root,one


def test_full_order_reconstruction_and_deterministic_overview(tmp_path):
    root,one=prepared(tmp_path)
    report,samples=verify(root,source_root=tmp_path,sample_limit=3)
    assert report['passed'] and report['total_points']==7
    assert report['sources'][0]['coverage_complete']
    assert report['sources'][0]['source_order_record_hash_matched']
    assert samples[0]['source_indices'].tolist()==[0,3,6]
    assert samples[0]['colors'][:,0].tolist()==[0,11,23]
    assert not list(tmp_path.glob('cospace-source-verify-*'))


@pytest.mark.parametrize('problem',['hash','duplicate','missing','records','tile','path','source','total'])
def test_bad_shards_and_source_changes_fail_closed(tmp_path,problem):
    root,one=prepared(tmp_path)
    manifest=root/'scene.json';scene=json.loads(manifest.read_bytes());source=scene['sources'][0];shard=source['shards'][0]
    path=root/shard['path']
    if problem=='hash':path.write_bytes(b'broken')
    if problem in ('duplicate','records'):
        with np.load(path,allow_pickle=False) as data:
            records=data['records'];ids=data['source_indices']
        if problem=='duplicate':ids[:]=0
        else:records['intensity']+=1
        np.savez_compressed(path,records=records,source_indices=ids)
        shard.update(sha256=digest(path),bytes=path.stat().st_size)
    if problem=='missing':source['shards'].pop()
    if problem=='tile':shard['tile'][0]+=1
    if problem=='path':shard['path']='../one.laz'
    if problem=='source':one[0].write_bytes(b'mutated')
    if problem=='total':scene['total_points']+=1
    manifest.write_text(json.dumps(scene),encoding='utf-8')
    with pytest.raises(ValueError):verify(root,source_root=tmp_path)
    assert not list(tmp_path.glob('cospace-source-verify-*'))


def test_overview_inputs_are_explicit_samples_and_originals_stay_unchanged(tmp_path):
    from experiments.scripts.verify_scene_pointclouds import generate
    from packages.data.preview_pointcloud import read_cloud
    root,one=prepared(tmp_path)
    before=one[0].read_bytes()
    report=generate(root,tmp_path/'overview',source_root=tmp_path,sample_limit=3)
    checked,points,colors,doc=read_cloud(tmp_path/'overview/source-00/snapshot')
    assert report['total_points']==7 and report['overview_points']==3
    assert not report['product_full_resolution_build_completed']
    assert checked['point_count']==3 and checked['scope']=='scene_local'
    assert doc['provenance']['source_member_sha256']==digest(one[0])
    assert '不是全量构建模型' in doc['provenance']['description']
    assert one[0].read_bytes()==before
    html=(tmp_path/'overview/index.html').read_text(encoding='utf-8')
    assert '__SCENE_DATA__' not in html and 'one.laz' in html
    with pytest.raises(ValueError,match='exclusive'):
        generate(root,tmp_path/'overview',source_root=tmp_path,sample_limit=3)


def test_overview_names_cannot_break_out_of_script():
    from experiments.scripts.verify_scene_pointclouds import overview_html
    sample=dict(name='</script><script>alert(1)</script>',points=np.array([[1.,2.,3.]]),colors=np.array([[1,2,3]]))
    html=overview_html([sample],1,'assumed_metre_for_flow_validation')
    assert '</script><script>alert(1)</script>' not in html
    assert '\\u003c/script>' in html
    encoded=html.split('const sources=',1)[1].split(';\nconst canvas=',1)[0]
    assert json.loads(encoded)[0]['name']==sample['name']
