"""Run in experiments/ifc-tool; the production environment has no native parser."""
import gc
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
