import copy
import io
import json
from pathlib import Path
import numpy as np
import pytest
from packages.data.ifc_inspection import inspect_ifc,digest,mesh_arrays
from packages.data.ifc_workspace import IfcConfig,load_mesh,validate_catalog


VERTICES=np.array([[0.,0.,0.],[2.,0.,0.],[0.,3.,0.],[0.,0.,4.]])
FACES=np.array([[0,1,2],[0,1,3],[0,2,3],[1,2,3]])


def fake_reader(path,failed=False):
    metadata=dict(schema='IFC4X3',parser='test_double',parser_version='0',project_name='test',length_unit='METRE',
        metres_per_unit=1.,projected_crs=[],map_conversions=[],sites=[])
    rows=[(dict(step_id=1,global_id='building',ifc_type='IfcBuilding',name='Building',container_id=None,
        placement_m=np.eye(4).tolist(),geometry_status='no_representation'),None,None),
        (dict(step_id=2,global_id='wall',ifc_type='IfcWall',name='Wall',container_id='building',
        placement_m=np.eye(4).tolist(),geometry_status='extracted'),VERTICES.copy(),FACES.copy())]
    if failed:rows.append((dict(step_id=3,global_id='door',ifc_type='IfcDoor',name='Door',container_id='building',
        placement_m=np.eye(4).tolist(),geometry_status='extraction_failed'),None,None))
    return metadata,iter(rows)


def assets_at(root,space,*,failed=False):
    root.mkdir(parents=True,exist_ok=True);source=root/'original.ifc';source.write_bytes(b'test fixture; not a parseable IFC')
    output=root/'catalog';doc=inspect_ifc(source,output,expected_sha256=digest(source),reader=lambda p:fake_reader(p,failed))
    config=root/'bindings.json';config.write_text(json.dumps(dict(profile='cospace.scene-ifc-bindings/0.1',
        bindings=[dict(space_id=space,root=str(output.resolve()),catalog_sha256=digest(output/'ifc.json'))])))
    return config,doc,output


def test_inspection_catalog_all_products_and_mesh_binding(tmp_path):
    config,doc,root=assets_at(tmp_path,'space-'+'1'*16,failed=True)
    assert doc['state']=='geometry_partial' and doc['product_count']==3
    assert doc['geometry_counts']=={'extracted':1,'no_representation':1,'extraction_failed':1}
    assert doc['bounds_m']==[[0.,0.,0.],[2.,3.,4.]] and doc['vertices']==4 and doc['triangles']==4
    assert doc['alignment_verified'] is False and doc['robot_ready'] is False
    assert validate_catalog(doc)==doc
    v,f=load_mesh(root,doc['products'][1]);assert np.array_equal(v,VERTICES) and np.array_equal(f,FACES)
    assert json.loads((root/'inspection-state.json').read_bytes())['catalog_sha256']==digest(root/'ifc.json')
    assert IfcConfig.model_validate_json(config.read_bytes()).bindings[0].space_id=='space-'+'1'*16


@pytest.mark.parametrize('problem',['digest','existing','source_change','geometry_budget','duplicate','invalid_vertices','empty','status'])
def test_inspection_failures_never_publish_catalog(tmp_path,monkeypatch,problem):
    source=tmp_path/'source.ifc';source.write_bytes(b'fixture');expected=digest(source);output=tmp_path/'out'
    def reader(path):
        metadata,iterator=fake_reader(path);rows=list(iterator)
        if problem=='source_change':source.write_bytes(b'changed')
        if problem=='duplicate':rows[1][0]['global_id']='building'
        if problem=='invalid_vertices':rows[1][1][0,0]=np.nan
        if problem=='empty':rows=[]
        if problem=='status':rows[1][0]['geometry_status']='invented'
        return metadata,iter(rows)
    if problem=='geometry_budget':monkeypatch.setattr('packages.data.ifc_inspection.MAX_VERTICES',3)
    if problem=='existing':output.mkdir()
    with pytest.raises(ValueError):inspect_ifc(source,output,expected_sha256='0'*64 if problem=='digest' else expected,reader=reader)
    assert not (output/'ifc.json').exists()
    if (output/'inspection-state.json').exists():assert json.loads((output/'inspection-state.json').read_bytes())['state']=='failed'


@pytest.mark.parametrize('vertices,faces',[(VERTICES,np.array([[0,1,9]])),(VERTICES,np.array([[0.,1.,2.]])),
    (VERTICES.reshape(-1),FACES),(VERTICES,np.array([[-1,1,2]])),(VERTICES,np.empty((0,3),dtype=int))])
def test_invalid_mesh_layout_rejected(vertices,faces):
    with pytest.raises(ValueError):mesh_arrays(vertices,faces)


def test_mesh_changed_inner_size_and_bounds_refused(tmp_path):
    _,doc,root=assets_at(tmp_path,'space-'+'1'*16);product=doc['products'][1];path=root/'e00001.npz';original=path.read_bytes()
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):load_mesh(root,product)
    path.write_bytes(original);changed=copy.deepcopy(product);changed['bounds_m'][1][0]=9.
    with pytest.raises(ValueError,match='bounds'):load_mesh(root,changed)
    # Declared array lengths checked before a reader can allocate an oversized mesh.
    changed=copy.deepcopy(product);changed['mesh']['vertices']=1
    large=io.BytesIO();np.savez_compressed(large,vertices=np.tile(VERTICES,(100,1)),faces=FACES.astype('<i4'))
    path.write_bytes(large.getvalue());changed['mesh'].update(bytes=path.stat().st_size,sha256=digest(path))
    with pytest.raises(ValueError,match='archive_budget'):load_mesh(root,changed)


def test_schema_matches_runtime():
    schema=json.loads(Path('contracts/schemas/scene-ifc-bindings-v0.1.schema.json').read_bytes())
    assert schema==IfcConfig.model_json_schema()
