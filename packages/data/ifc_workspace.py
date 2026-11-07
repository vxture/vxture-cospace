"""Scene-authorized IFC evidence and geometry previews; no implicit adoption."""
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Literal
import zipfile

import numpy as np
from pydantic import BaseModel,ConfigDict,Field
from packages.data.ifc_inspection import PROFILE,MAX_PRODUCTS,MAX_VERTICES,MAX_FACES,MAX_SOURCE_BYTES,digest,mesh_arrays


class Fixed(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)


class IfcBinding(Fixed):
    space_id:str=Field(pattern='^space-[a-f0-9]{16}$')
    root:str=Field(min_length=1)
    catalog_sha256:str=Field(pattern='^[a-f0-9]{64}$')


class IfcConfig(Fixed):
    profile:Literal['cospace.scene-ifc-bindings/0.1']
    bindings:list[IfcBinding]=Field(max_length=1000)


def read_json(path,limit):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('ifc_json_budget')
    return raw,json.loads(raw)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def validate_catalog(doc):
    products=doc['products']
    if (doc['profile']!=PROFILE or doc['unit']!='m' or doc['alignment_verified'] is not False
            or doc['quality']!='unverified' or doc['robot_ready'] is not False
            or doc['state'] not in ('geometry_partial','geometry_extracted')
            or not 1<=len(products)<=MAX_PRODUCTS or doc['product_count']!=len(products)
            or len({p['global_id'] for p in products})!=len(products)
            or doc['frame_id']!='ifc_world_'+doc['source']['sha256'][:16]
            or doc['source'].get('path')!='source.ifc' or type(doc['source']['bytes']) is not int
            or not 1<=doc['source']['bytes']<=MAX_SOURCE_BYTES):raise ValueError('ifc_catalog_binding')
    total_vertices=total_faces=0
    for i,p in enumerate(products):
        if p['geometry_status']=='extracted':
            mesh=p['mesh']
            if (mesh['path']!=f'e{i:05}.npz' or type(mesh['vertices']) is not int or not 1<=mesh['vertices']<=MAX_VERTICES
                    or type(mesh['triangles']) is not int or not 1<=mesh['triangles']<=MAX_FACES
                    or type(mesh['bytes']) is not int or not 1<=mesh['bytes']<=64*1024*1024
                    or not re.fullmatch('[a-f0-9]{64}',mesh['sha256'])):raise ValueError('ifc_mesh_binding')
            total_vertices+=mesh['vertices'];total_faces+=mesh['triangles']
        elif p['geometry_status'] not in ('no_representation','extraction_failed'):raise ValueError('ifc_geometry_status_invalid')
    if total_vertices!=doc['vertices'] or total_faces!=doc['triangles'] or total_vertices>MAX_VERTICES or total_faces>MAX_FACES:
        raise ValueError('ifc_catalog_geometry_count')
    return doc


def validate_source(root,doc):
    path=Path(root)/'source.ifc'
    if (path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve())
            or path.stat().st_size!=doc['source']['bytes'] or digest(path)!=doc['source']['sha256']):
        raise ValueError('ifc_source_changed')


def load_mesh(root,product):
    member=product['mesh'];path=Path(root)/member['path']
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):raise ValueError('ifc_mesh_path')
    with path.open('rb') as stream:raw=stream.read(member['bytes']+1)
    if len(raw)!=member['bytes'] or sha(raw)!=member['sha256']:raise ValueError('ifc_mesh_changed')
    # Check inner array sizes before NumPy allocates buffers.
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist()
        if (len(entries)!=2 or {p.filename for p in entries}!={'vertices.npy','faces.npy'}
                or archive.getinfo('vertices.npy').file_size>member['vertices']*24+1024
                or archive.getinfo('faces.npy').file_size>member['triangles']*12+1024):raise ValueError('ifc_mesh_archive_budget')
    with np.load(io.BytesIO(raw),allow_pickle=False) as arrays:vertices,faces=mesh_arrays(arrays['vertices'],arrays['faces'])
    if len(vertices)!=member['vertices'] or len(faces)!=member['triangles']:raise ValueError('ifc_mesh_count')
    bounds=np.array([vertices.min(axis=0),vertices.max(axis=0)])
    if not np.array_equal(bounds,np.asarray(product['bounds_m'])):raise ValueError('ifc_mesh_bounds')
    return vertices,faces


class IfcWorkspace:
    def __init__(self,directory,jobs,config=None):self.directory,self.jobs,self.config=directory,jobs,Path(config) if config else None

    def catalog(self,space,expected=None):
        self.directory.read('space',space)
        if self.config is None:return None,None
        _,raw=read_json(self.config,1_000_000);config=IfcConfig.model_validate(raw)
        if len({b.space_id for b in config.bindings})!=len(config.bindings):raise ValueError('ifc_duplicate_scene_binding')
        binding=next((b for b in config.bindings if b.space_id==space),None)
        if binding is None:return None,None
        if expected is not None and expected!=binding.catalog_sha256:raise ValueError('ifc_catalog_changed')
        raw,doc=read_json(Path(binding.root)/'ifc.json',8*1024*1024)
        if sha(raw)!=binding.catalog_sha256:raise ValueError('ifc_catalog_changed')
        validate_catalog(doc);validate_source(binding.root,doc)
        return binding,doc

    def directory_view(self,space):
        binding,doc=self.catalog(space)
        if binding is None:return dict(profile='cospace.ifc-workspace/0.1',space_id=space,configured=False)
        return {k:v for k,v in doc.items() if k!='products'}|dict(profile='cospace.ifc-workspace/0.1',space_id=space,
            configured=True,catalog_sha256=binding.catalog_sha256,
            products=[{k:v for k,v in p.items() if k not in ('mesh','placement_m')}|dict(element_id=f'e{i:05}') for i,p in enumerate(doc['products'])])

    def element(self,space,identity,expected):
        binding,doc=self.catalog(space,expected)
        if binding is None:raise ValueError('ifc_not_configured')
        if not re.fullmatch('e[0-9]{5}',identity) or int(identity[1:])>=len(doc['products']):raise ValueError('ifc_element_unknown')
        product=doc['products'][int(identity[1:])]
        if product['geometry_status']!='extracted':raise ValueError('ifc_element_geometry_unavailable')
        vertices,_=load_mesh(binding.root,product)
        return binding,doc,product,vertices

    def preview(self,space,identity,expected):
        _,doc,product,vertices=self.element(space,identity,expected)
        stride=max(1,int(np.ceil(len(vertices)/10000)));points=vertices[::stride].tolist()
        return dict(profile='cospace.ifc-element-preview/0.1',space_id=space,catalog_sha256=expected,
            element_id=identity,global_id=product['global_id'],unit='m',frame_id=doc['frame_id'],axes=['ifc_x','ifc_y','ifc_z'],
            appearance='ifc_tessellated_vertices',point_count=len(vertices),bounds=product['bounds_m'],points=points,
            colors=[[70,110,210]]*len(points),sampling=dict(method='file_index_stride',stride=stride,count=len(points),limit=10000),
            alignment_verified=False,quality='unverified',robot_ready=False)
