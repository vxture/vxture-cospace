"""Run in the dedicated native IFC environment, never in the HTTP interpreter."""
import gc
from pathlib import Path
import numpy as np
import pytest
ifcopenshell=pytest.importorskip('ifcopenshell')
from packages.data.ifc_inspection import native_reader,inspect_ifc,digest


def fixture(path):
    doc=ifcopenshell.file(schema='IFC4X3_ADD2')
    def entity(name,**kwargs):return doc.create_entity(name,**kwargs)
    unit=entity('IfcSIUnit',UnitType='LENGTHUNIT',Prefix='MILLI',Name='METRE')
    assignment=entity('IfcUnitAssignment',Units=[unit])
    origin=entity('IfcCartesianPoint',Coordinates=(0.,0.,0.))
    world=entity('IfcAxis2Placement3D',Location=origin)
    context=entity('IfcGeometricRepresentationContext',ContextIdentifier='Body',ContextType='Model',CoordinateSpaceDimension=3,Precision=.001,WorldCoordinateSystem=world)
    entity('IfcProject',GlobalId=ifcopenshell.guid.new(),Name='Millimetre fixture',UnitsInContext=assignment,RepresentationContexts=[context])
    location=entity('IfcCartesianPoint',Coordinates=(10000.,20000.,30000.))
    direction=entity('IfcDirection',DirectionRatios=(0.,1.,0.))
    axis=entity('IfcAxis2Placement3D',Location=location,RefDirection=direction)
    placement=entity('IfcLocalPlacement',RelativePlacement=axis)
    points=entity('IfcCartesianPointList3D',CoordList=[(0.,0.,0.),(1000.,0.,0.),(0.,1000.,0.),(0.,0.,1000.)])
    faces=entity('IfcTriangulatedFaceSet',Coordinates=points,Closed=True,CoordIndex=[(1,3,2),(1,2,4),(1,4,3),(2,3,4)])
    shape=entity('IfcShapeRepresentation',ContextOfItems=context,RepresentationIdentifier='Body',RepresentationType='Tessellation',Items=[faces])
    definition=entity('IfcProductDefinitionShape',Representations=[shape])
    entity('IfcWall',GlobalId=ifcopenshell.guid.new(),Name='Rotated millimetre wall',ObjectPlacement=placement,Representation=definition)
    doc.write(str(path))


def test_native_document_lifetime_units_and_world_placement(tmp_path):
    source=tmp_path/'mm.ifc';fixture(source)
    metadata,rows=native_reader(source)
    gc.collect() # Entity handles must retain their native document through iteration.
    product,vertices,faces=next(rows)
    assert metadata['metres_per_unit']==.001 and product['geometry_status']=='extracted'
    assert np.allclose(vertices.min(axis=0),[9,20,30]) and np.allclose(vertices.max(axis=0),[10,21,31])
    assert np.allclose(np.array(product['placement_m'])[:3,3],[10,20,30])
    report=inspect_ifc(source,tmp_path/'out',expected_sha256=digest(source))
    assert report['product_count']==1 and report['vertices']==4 and report['triangles']==4
    assert report['geometry_counts']=={'extracted':1} and not report['alignment_verified']


def test_structure_candidate_preserves_declared_edges_and_geometry(tmp_path):
    from packages.data.ifc_structure import inspect_ifc_structure

    source = tmp_path/'structure.ifc'
    fixture(source)
    model = ifcopenshell.open(str(source))

    def create(kind, **fields):
        return model.create_entity(kind, GlobalId=ifcopenshell.guid.new(), **fields)

    building = create('IfcBuilding')
    level = create('IfcBuildingStorey')
    door = create('IfcDoor')
    stair = create('IfcStair')
    flight = create('IfcStairFlight')
    opening = create('IfcOpeningElement')
    wall = model.by_type('IfcWall')[0]
    create('IfcRelAggregates', RelatingObject=building, RelatedObjects=[level])
    create('IfcRelAggregates', RelatingObject=stair, RelatedObjects=[flight])
    create('IfcRelContainedInSpatialStructure', RelatingStructure=level, RelatedElements=[door, wall, stair])
    create('IfcRelVoidsElement', RelatingBuildingElement=wall, RelatedOpeningElement=opening)
    create('IfcRelFillsElement', RelatingOpeningElement=opening, RelatedBuildingElement=door)
    model.write(str(source))
    pinned = digest(source)
    report = inspect_ifc_structure(source, tmp_path/'candidate', expected_sha256=pinned)
    assert digest(source) == pinned
    assert report['source']['sha256'] == pinned
    assert not report['alignment_verified']
    structure = report['structure']
    assert structure['missing_declared_roles'] == ['space', 'distribution_board']
    assert structure['assessment'] == 'unverified'
    assert {e['geometry_product_id'] for e in structure['entities']} == {p['global_id'] for p in report['products']}
    assert {(r['kind'], r['source_id'], r['target_id']) for r in structure['relations']} == {
        ('aggregates', building.GlobalId, level.GlobalId),
        ('aggregates', stair.GlobalId, flight.GlobalId),
        ('contained_in', door.GlobalId, level.GlobalId),
        ('contained_in', wall.GlobalId, level.GlobalId),
        ('contained_in', stair.GlobalId, level.GlobalId),
        ('opening_in', opening.GlobalId, wall.GlobalId),
        ('fills', door.GlobalId, opening.GlobalId),
    }
    products = {p['global_id']: p for p in report['products']}
    assert products[wall.GlobalId]['mesh']['triangles'] == 4
    assert products[door.GlobalId]['geometry_status'] == 'no_representation'


def test_structure_candidate_requires_fixed_source(tmp_path):
    from packages.data.ifc_structure import inspect_ifc_structure

    source = tmp_path/'structure.ifc'
    fixture(source)
    with pytest.raises(ValueError, match='ifc_source_digest_mismatch'):
        inspect_ifc_structure(source, tmp_path/'candidate', expected_sha256='0'*64)
    assert not (tmp_path/'candidate').exists()


def test_structure_cli_path_boundaries(tmp_path, monkeypatch):
    from experiments.scripts import inspect_ifc_structure as cli

    root = tmp_path/'sources'
    root.mkdir()
    inside, outside = root/'inside.ifc', tmp_path/'outside.ifc'
    inside.write_bytes(b'fixture')
    outside.write_bytes(b'fixture')
    monkeypatch.setenv('COSPACE_SCENE_INPUT_ROOT', str(root))
    monkeypatch.setattr(cli, 'OUTPUT_ROOT', tmp_path/'output')
    assert cli.source_path(inside.relative_to(root)) == inside
    with pytest.raises(ValueError, match='relative_ifc_required'):
        cli.source_path(inside)
    with pytest.raises(ValueError, match='source_outside_allowed_root'):
        cli.source_path(Path('../outside.ifc'))
    with pytest.raises(ValueError, match='invalid_run_id'):
        cli.output_path('../outside')
