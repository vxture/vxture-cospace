"""Offline IFC geometry inspection. Native IFC parsing is never an HTTP upload path."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

PROFILE='cospace.ifc-inspection/0.1'
MAX_SOURCE_BYTES=128*1024*1024
MAX_PRODUCTS=10_000
MAX_VERTICES=2_000_000
MAX_FACES=4_000_000
MAX_OUTPUT_BYTES=192*1024*1024


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def dump(path,doc):
    path.write_text(json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def mesh_arrays(vertices,faces):
    vertices=np.asarray(vertices,dtype=np.float64)
    faces=np.asarray(faces)
    if (vertices.ndim!=2 or vertices.shape[1]!=3 or not 1<=len(vertices)<=MAX_VERTICES
            or not np.isfinite(vertices).all() or np.abs(vertices).max()>10_000_000
            or faces.ndim!=2 or faces.shape[1]!=3 or not 1<=len(faces)<=MAX_FACES
            or faces.dtype.kind not in 'iu' or faces.min()<0 or faces.max()>=len(vertices)):
        raise ValueError('ifc_mesh_layout_or_budget')
    return vertices,faces.astype('<i4')


def native_reader(path):
    try:
        import ifcopenshell
        import ifcopenshell.geom
        import ifcopenshell.util.element
        import ifcopenshell.util.placement
        import ifcopenshell.util.unit
    except ImportError as exc:raise ValueError('install_isolated_ifc_preprocessing_dependencies') from exc
    document=ifcopenshell.open(str(path))
    if not document.schema.startswith('IFC4'):raise ValueError('ifc_schema_not_supported')
    projects=document.by_type('IfcProject')
    if len(projects)!=1:raise ValueError('ifc_requires_one_project')
    # Unit utility defaults to 1 if no unit exists: explicitly reject that ambiguity.
    assignment=projects[0].UnitsInContext
    units=[u for u in assignment.Units if getattr(u,'UnitType',None)=='LENGTHUNIT'] if assignment else []
    if len(units)!=1:raise ValueError('ifc_length_unit_missing_or_ambiguous')
    scale=ifcopenshell.util.unit.calculate_unit_scale(document)
    if not np.isfinite(scale) or scale<=0:raise ValueError('ifc_length_unit_invalid')
    products=document.by_type('IfcProduct')
    if not 1<=len(products)<=MAX_PRODUCTS:raise ValueError('ifc_product_budget')
    metadata=dict(schema=document.schema,parser='ifcopenshell',parser_version=ifcopenshell.version,
        project_name=projects[0].Name or '',length_unit=str(units[0]),metres_per_unit=float(scale),
        projected_crs=[dict(name=c.Name or '',map_projection=getattr(c,'MapProjection',None),map_zone=getattr(c,'MapZone',None))
                       for c in document.by_type('IfcProjectedCRS')],
        map_conversions=[dict(entity=c.is_a(),step_id=c.id()) for c in document.by_type('IfcMapConversion')],
        sites=[dict(global_id=s.GlobalId,latitude=list(s.RefLatitude) if s.RefLatitude else None,
                    longitude=list(s.RefLongitude) if s.RefLongitude else None,elevation=s.RefElevation)
               for s in document.by_type('IfcSite')])
    settings=ifcopenshell.geom.settings()
    settings.set('use-world-coords',True)
    settings.set('convert-back-units',False)
    def rows(document=document):
        # Entity handles do not own the native file; retain it for the generator lifetime.
        for product in sorted(products,key=lambda p:p.id()):
            container=ifcopenshell.util.element.get_container(product)
            parent=product.ObjectPlacement
            # IFC placement matrices retain declared units; geometry returns SI metres.
            matrix=ifcopenshell.util.placement.get_local_placement(parent) if parent else np.eye(4)
            matrix=np.asarray(matrix,dtype=float).copy();matrix[:3,3]*=scale
            row=dict(step_id=product.id(),global_id=product.GlobalId,ifc_type=product.is_a(),name=product.Name or '',
                container_id=container.GlobalId if container else None,placement_m=matrix.tolist(),
                geometry_status='no_representation' if not product.Representation else 'pending')
            if not product.Representation:yield row,None,None;continue
            try:
                shape=ifcopenshell.geom.create_shape(settings,product)
                vertices=np.asarray(shape.geometry.verts,dtype=float).reshape(-1,3)
                faces=np.asarray(shape.geometry.faces,dtype=np.int64).reshape(-1,3)
                if not len(vertices) or not len(faces):raise ValueError('empty_geometry')
            except (RuntimeError,ValueError):
                row['geometry_status']='extraction_failed';yield row,None,None;continue
            row['geometry_status']='extracted';yield row,vertices,faces
    return metadata,rows()


def inspect_ifc(source,output,*,expected_sha256,reader=native_reader,progress=None):
    source,output=Path(source).absolute(),Path(output).absolute()
    if source.is_symlink() or not source.is_file() or not 1<=source.stat().st_size<=MAX_SOURCE_BYTES:
        raise ValueError('ifc_source_invalid_or_budget')
    if digest(source)!=expected_sha256:raise ValueError('ifc_source_digest_mismatch')
    if output.exists() or source.resolve().is_relative_to(output.resolve()):raise ValueError('ifc_exclusive_output_required')
    metadata,rows=reader(source)
    output.mkdir(parents=True);dump(output/'inspection-state.json',dict(state='running'))
    products=[];seen=set();total_vertices=total_faces=output_bytes=0;lo=hi=None
    try:
        for row,vertices,faces in rows:
            if len(products)>=MAX_PRODUCTS:raise ValueError('ifc_product_budget')
            guid=row['global_id']
            if not isinstance(guid,str) or not guid or guid in seen:raise ValueError('ifc_duplicate_or_missing_global_id')
            seen.add(guid)
            matrix=np.asarray(row['placement_m'],dtype=float)
            if matrix.shape!=(4,4) or not np.isfinite(matrix).all():raise ValueError('ifc_placement_invalid')
            if row['geometry_status']=='extracted':
                vertices,faces=mesh_arrays(vertices,faces)
                total_vertices+=len(vertices);total_faces+=len(faces)
                if total_vertices>MAX_VERTICES or total_faces>MAX_FACES:raise ValueError('ifc_total_geometry_budget')
                bounds=[vertices.min(axis=0).tolist(),vertices.max(axis=0).tolist()]
                lo=np.minimum(lo,bounds[0]) if lo is not None else np.array(bounds[0])
                hi=np.maximum(hi,bounds[1]) if hi is not None else np.array(bounds[1])
                name=f'e{len(products):05}.npz';path=output/name
                np.savez_compressed(path,vertices=vertices,faces=faces)
                row.update(bounds_m=bounds,centroid_m=vertices.mean(axis=0).tolist(),
                    mesh=dict(path=name,sha256=digest(path),bytes=path.stat().st_size,vertices=len(vertices),triangles=len(faces)))
                output_bytes+=path.stat().st_size
                if output_bytes>MAX_OUTPUT_BYTES:raise ValueError('ifc_output_budget')
            elif row['geometry_status'] not in ('no_representation','extraction_failed'):
                raise ValueError('ifc_geometry_status_invalid')
            products.append(row)
            if progress:progress(dict(products=len(products),vertices=total_vertices,triangles=total_faces))
        if not products or lo is None:raise ValueError('ifc_no_extracted_geometry')
        shutil.copyfile(source,output/'source.ifc')
        if digest(source)!=expected_sha256 or digest(output/'source.ifc')!=expected_sha256:raise ValueError('ifc_source_changed')
        statuses=dict(Counter(p['geometry_status'] for p in products))
        doc=dict(profile=PROFILE,source=dict(name=source.name,path='source.ifc',sha256=expected_sha256,bytes=source.stat().st_size),
            **metadata,unit='m',frame_id='ifc_world_'+expected_sha256[:16],geometry_settings=dict(world_coords=True,convert_back_units=False),
            bounds_m=[lo.tolist(),hi.tolist()],products=products,product_count=len(products),geometry_counts=statuses,
            vertices=total_vertices,triangles=total_faces,alignment_verified=False,quality='unverified',robot_ready=False,
            state='geometry_partial' if statuses.get('extraction_failed') else 'geometry_extracted',
            limitations=['ifc_world_frame_is_not_pointcloud_frame','site_latitude_longitude_is_not_a_coordinate_transform',
                         'tessellated_geometry_is_not_an_independent_accuracy_check','no_automatic_object_associations'])
        dump(output/'ifc.json',doc)
        if (output/'ifc.json').stat().st_size>8*1024*1024:raise ValueError('ifc_catalog_budget')
        dump(output/'inspection-state.json',dict(state='complete',catalog_sha256=digest(output/'ifc.json')))
        return doc
    except BaseException:
        (output/'ifc.json').unlink(missing_ok=True)
        dump(output/'inspection-state.json',dict(state='failed'))
        raise
