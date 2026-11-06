import json
from pathlib import Path
import zipfile
import numpy as np
import pytest
from packages.data.preview_pointcloud import read_cloud,SourceReceipt,FORMAT
from packages.data.input_uploads import InputUploads,UploadRejected,capabilities
from packages.data.input_facts import facts,FactsUnavailable
from packages.data.preview_preflight import preflight
from packages.construction.preview_pointcloud import build
from packages.construction.preview_model import digest
from experiments.scripts.pack_input_upload import pack
from test_preview_pointcloud import specimen,update
from test_input_uploads import catalog_at


def declared(root):
    doc=json.loads((root/'pointcloud.json').read_bytes())
    receipt={'profile':'cospace.pointcloud-source/0.1','basis':'user_declared_file','original_name':'office.ply',
             'cloud':doc['cloud'],'coordinates':doc['coordinates'],'description':'用户提供的局部空间点云，处理情况尚未独立核验'}
    save(root,receipt)
    return receipt


def save(root,receipt):
    (root/'source.json').write_text(json.dumps(receipt,ensure_ascii=False)+'\n',encoding='utf-8')
    update(root,lambda d:d.update(source_receipt_path='source.json',provenance={
        'kind':'existing_pointcloud','source_manifest_sha256':digest(root/'source.json'),
        'source_member_sha256':d['cloud']['sha256'],'description':receipt['description']}))


@pytest.mark.parametrize('rgb',[False,True])
def test_source_receipt_preserved_through_upload_preflight_facts_and_frozen_model(tmp_path,rgb):
    root=specimen(tmp_path,rgb);receipt=declared(root);raw=(root/'cloud.ply').read_bytes()
    bundle=tmp_path/'declared.zip';pack(root,None,bundle,FORMAT)
    catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    first=store.register(bundle,spaces[0],'declared','actor');identity=first['input']['id']
    assert not store.register(bundle,spaces[0],'renamed','other')['created']
    snapshot=Path(catalog.read(identity)['snapshot'])
    assert (snapshot/'source.json').read_bytes()==(root/'source.json').read_bytes()
    assert (snapshot/'cloud.ply').read_bytes()==raw
    assert preflight(catalog,identity)['status']=='passed'
    report=facts(catalog,identity,spaces[0]);assert not report['payload_checked']
    assert report['fields']['source_basis']['value']=='user_declared_file'
    assert report['fields']['original_name']['value']=='office.ply'
    assert report['fields']['source_description']['value']==receipt['description']
    assert report['fields']['scene_alignment']['status']=='unknown'
    metadata=build(snapshot,tmp_path/'frozen','frozen',catalog.read(identity))
    assert metadata['source']['source_receipt']==receipt
    assert not metadata['construction']['coordinate_transform_applied'] and not metadata['robot_ready']
    with np.load(tmp_path/'frozen/spatial.npz') as arr:np.testing.assert_array_equal(arr['points'],read_cloud(root)[1])
    assert (root/'cloud.ply').read_bytes()==raw


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(basis='verified_survey'),lambda r:r.update(profile='unknown'),
    lambda r:r.update(original_name='../cloud.ply'),lambda r:r.update(original_name='C:\\cloud.ply'),
    lambda r:r.update(original_name=' '),lambda r:r.update(original_name='a'*161),
    lambda r:r.update(original_name='a\nb.ply'),lambda r:r.update(description=' '),
    lambda r:r.update(actor='forged'),lambda r:r.update(space_id='forged'),
    lambda r:r['coordinates'].update(frame_id='other'),lambda r:r['coordinates'].update(unit='mm'),
    lambda r:r['cloud'].update(sha256='a'*64),lambda r:r['cloud'].update(points=3),
])
def test_receipt_invalid_or_inconsistent_even_with_recomputed_digest(tmp_path,mutation):
    root=specimen(tmp_path);receipt=declared(root);mutation(receipt);save(root,receipt)
    with pytest.raises(ValueError):read_cloud(root)


@pytest.mark.parametrize('case',['missing','tamper','hash','member','kind','description','duplicate','budget','path'])
def test_receipt_binding_failures(tmp_path,case):
    root=specimen(tmp_path);declared(root)
    if case=='missing':(root/'source.json').unlink()
    elif case=='tamper':(root/'source.json').write_bytes(b'changed')
    elif case=='budget':(root/'source.json').write_bytes(b' '*64_001)
    elif case=='duplicate':
        p=root/'source.json';p.write_text(p.read_text(encoding="utf-8").replace('"basis":','"basis":"forged","basis":'),encoding="utf-8")
        update(root,lambda d:d['provenance'].update(source_manifest_sha256=digest(p)))
    else:
        changes={'hash':lambda d:d['provenance'].update(source_manifest_sha256='0'*64),
                 'member':lambda d:d['provenance'].update(source_member_sha256='0'*64),
                 'kind':lambda d:d['provenance'].update(kind='derived_single_frame'),
                 'description':lambda d:d['provenance'].update(description='changed'),
                 'path':lambda d:d.update(source_receipt_path='../source.json')}
        update(root,changes[case])
    with pytest.raises((ValueError,OSError)):read_cloud(root)


def test_receipt_changed_after_registration_refuses_preflight_facts_build_and_repeat(tmp_path):
    root=specimen(tmp_path);declared(root);bundle=tmp_path/'input.zip';pack(root,None,bundle,FORMAT)
    catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    result=store.register(bundle,spaces[0],'original','actor');identity=result['input']['id'];record=catalog.read(identity)
    receipt=Path(record['snapshot'])/'source.json';receipt.write_bytes(b'changed')
    assert preflight(catalog,identity)['status']=='failed'
    with pytest.raises(FactsUnavailable):facts(catalog,identity,spaces[0])
    with pytest.raises(ValueError):catalog.resolve(identity)
    with pytest.raises(ValueError):build(record['snapshot'],tmp_path/'bad','bad',record)
    with pytest.raises(UploadRejected,match='existing_evidence_invalid'):store.register(bundle,spaces[0],'repeat','actor')
    assert len(catalog.list())==1 and not (tmp_path/'bad').exists()


@pytest.mark.parametrize('case',['missing','extra','foreign_format'])
def test_zip_membership_requires_explicit_receipt_declaration(tmp_path,case):
    root=specimen(tmp_path);declared(root);original=tmp_path/'input.zip';pack(root,None,original,FORMAT)
    bundle=tmp_path/'bad.zip'
    with zipfile.ZipFile(original) as src,zipfile.ZipFile(bundle,'w') as dst:
        for name in src.namelist():
            raw=src.read(name)
            if case=='missing' and name=='snapshot/source.json':continue
            if case=='extra' and name=='snapshot/pointcloud.json':
                d=json.loads(raw);d.pop('source_receipt_path');raw=json.dumps(d).encode()
            if case=='foreign_format' and name=='input.json':raw=b'{"profile":"cospace.input-upload/0.1","format":"ros1_lidar_single_frame"}'
            dst.writestr(name,raw)
    catalog,spaces=catalog_at(tmp_path)
    with pytest.raises(UploadRejected):InputUploads(catalog).register(bundle,spaces[0],'bad','actor')
    assert not catalog.list()


def test_new_declaration_creates_new_record_same_coordinates_and_scene(tmp_path):
    root=specimen(tmp_path);receipt=declared(root);one=tmp_path/'one.zip';pack(root,None,one,FORMAT)
    receipt['description']='补充来源说明，不代表现场变化';save(root,receipt);two=tmp_path/'two.zip';pack(root,None,two,FORMAT)
    catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    a=store.register(one,spaces[0],'one','actor');b=store.register(two,spaces[0],'two','actor')
    assert a['input']['id']!=b['input']['id'] and a['input']['cloud_sha256']==b['input']['cloud_sha256']
    assert a['input']['space_id']==b['input']['space_id']==spaces[0]
    assert a['input']['snapshot_sha256']!=b['input']['snapshot_sha256']


def test_receipt_schema_and_capability_match_runtime():
    schema=json.loads(Path('contracts/schemas/pointcloud-source-v0.1.schema.json').read_bytes())
    assert {k:v for k,v in schema.items() if k!='$schema'}==SourceReceipt.model_json_schema()
    value=capabilities()['pointcloud_preparation']
    assert value['profile']=='cospace.pointcloud-preparation/0.1'
    assert value['source_profile']=='cospace.pointcloud-source/0.1'
    assert value['max_cloud_bytes']==32*1024*1024 and value['max_points']==1_000_000
