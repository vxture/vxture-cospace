"""Fixed-publication surface partitions. Queries decode only intersecting members.

An externally recorded index digest is the trust anchor. Untouched partitions
are not claimed verified, and missing evidence never means traversable space.
"""
from collections import defaultdict
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zipfile
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.lifecycle.preview_scope import match, owned
from packages.spatial.preview_range import range_indices, surface_range, DEFAULT_RANGE_CELLS

PROFILE='cospace.partitioned-agent/0.1'
MAX_CELLS=500_000
MAX_TILE_CELLS=4096
MAX_TILES=1024
MAX_BYTES=32*1024*1024
MAX_INDEX_BYTES=2*1024*1024
MAX_QUERY_TILES=64
MAX_QUERY_CELLS=65_536
GRID_CELLS=256


def sha(raw):return hashlib.sha256(raw).hexdigest()


class Member(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    sha256:str=Field(pattern='^[a-f0-9]{64}$')
    bytes:int=Field(ge=1,le=MAX_BYTES)


class Partition(Member):
    id:str=Field(pattern='^p[0-9]{5}$')
    cells:int=Field(ge=1,le=MAX_TILE_CELLS)
    cell_bounds:list[list[int]]=Field(min_length=2,max_length=2)

    @model_validator(mode='after')
    def valid(self):
        if (self.bytes!=self.cells*24 or any(len(row)!=3 for row in self.cell_bounds)
                or any(abs(v)>10**12 for row in self.cell_bounds for v in row)
                or any(a>=b for a,b in zip(*self.cell_bounds))):raise ValueError('partition_layout')
        return self


class PartitionIndex(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    profile:Literal['cospace.partitioned-agent/0.1']
    publication_id:str=Field(pattern='^preview-[a-f0-9]{16}$')
    model_id:str=Field(min_length=1,max_length=160)
    space_id:str|None=None
    project_id:str|None=None
    model_manifest_sha256:str=Field(pattern='^[a-f0-9]{64}$')
    source_model_sha256:str=Field(pattern='^[a-f0-9]{64}$')
    source_agent_sha256:str=Field(pattern='^[a-f0-9]{64}$')
    canonical_cells_sha256:str=Field(pattern='^[a-f0-9]{64}$')
    frame_id:str=Field(min_length=1,max_length=256)
    resolution_m:float=Field(ge=0.000001,le=1000)
    total_cells:int=Field(ge=1,le=MAX_CELLS)
    max_tile_cells:Literal[4096]
    source_files:dict[str,Member]
    partitions:list[Partition]=Field(min_length=1,max_length=MAX_TILES)
    coverage:Literal['surface_evidence_only']
    quality:Literal['unverified']
    robot_ready:Literal[False]
    layout:Literal['little_endian_int64_xyz']
    selection_rule:Literal['cell_center_in_half_open_aabb']

    @model_validator(mode='after')
    def valid(self):
        if (self.robot_ready or set(self.source_files)!={'publication.json','model.json'}
                or self.total_cells!=sum(t.cells for t in self.partitions)
                or [p.id for p in self.partitions]!=[f'p{i:05}' for i in range(len(self.partitions))]):
            raise ValueError('partition_index_binding')
        for i,a in enumerate(self.partitions):
            if any(intersects(a.cell_bounds,b.cell_bounds) for b in self.partitions[:i]):
                raise ValueError('partition_bounds_overlap')
        return self


def intersects(a,b):return all(a[0][i]<a[1][i] and b[0][i]<b[1][i] and a[0][i]<b[1][i] and b[0][i]<a[1][i] for i in range(3))


def encoded(cells):return np.asarray(cells,dtype='<i8').reshape(-1,3).tobytes()


def source_binding(doc,files):
    record=json.loads(files['publication.json']);model=json.loads(files['model.json'])
    match(doc,owned(record));match(model,owned(record))
    if (record['profile']!='cospace.local-preview-publication/0.1' or record['id']!=doc['publication_id']
            or model['profile']!='cospace.real-model-preview/0.1' or model['id']!=record['candidate_id']
            or model['id']!=doc['model_id'] or model['frame_id']!=doc['frame_id']
            or sha(files['model.json'])!=doc['model_manifest_sha256']
            or record['model_manifest_sha256']!=doc['model_manifest_sha256']
            or record['files']['model.json']!={'sha256':sha(files['model.json']),'bytes':len(files['model.json'])}
            or record['source_model_sha256']!=doc['source_model_sha256']
            or model['members']['spatial.npz']['sha256']!=doc['source_model_sha256']
            or record['files']['agent.npz']['sha256']!=model['members']['agent.npz']['sha256']
            or ('bytes' in model['members']['agent.npz'] and record['files']['agent.npz']['bytes']!=model['members']['agent.npz']['bytes'])
            or model['members']['agent.npz']['sha256']!=doc['source_agent_sha256']
            or model['agent_view']['resolution_m']!=doc['resolution_m']
            or model['agent_view'].get('surface_cells',doc['total_cells'])!=doc['total_cells']
            or record.get('derivation')!=model.get('derivation')):
        raise ValueError('partition_source_binding')
    from packages.construction.preview_derivations import validate_composition
    validate_composition(model)
    return record,model


def export_partitions(record,model):
    """Caller must read a validated, distributing publication before export."""
    files={n:(model.root/n).read_bytes() for n in ('publication.json','model.json')}
    if json.loads(files['publication.json'])!=record:raise ValueError('partition_publication_changed')
    cells=sorted(model.cells)
    if (not 1<=len(cells)<=MAX_CELLS or any(len(c)!=3 or any(type(v)is not int or abs(v)>=10**12 for v in c) for c in cells)):
        raise ValueError('partition_source_cells_budget')
    # Check the original agent member as well as the already-loaded model set.
    agent=(model.root/'agent.npz').read_bytes()
    if sha(agent)!=model.manifest['members']['agent.npz']['sha256']:raise ValueError('partition_source_changed')
    with np.load(io.BytesIO(agent),allow_pickle=False) as arrays:
        original=arrays['cells']
        if original.dtype.kind not in 'iu' or original.shape!=(len(cells),3) or encoded(sorted(map(tuple,original.tolist())))!=encoded(cells):
            raise ValueError('partition_source_cell_mismatch')
    groups=defaultdict(list)
    for cell in cells:groups[tuple(v//GRID_CELLS for v in cell)].append(cell)
    partitions=[]
    def split(rows):
        if len(rows)>MAX_TILE_CELLS:
            lo=[min(c[i] for c in rows) for i in range(3)];hi=[max(c[i] for c in rows) for i in range(3)]
            axis=max(range(3),key=lambda i:hi[i]-lo[i]);middle=(lo[axis]+hi[axis]+1)//2
            split([r for r in rows if r[axis]<middle]);split([r for r in rows if r[axis]>=middle]);return
        if len(partitions)>=MAX_TILES:raise ValueError('partition_count_budget')
        identity=f'p{len(partitions):05}';raw=encoded(rows);files[f'{identity}.bin']=raw
        partitions.append(dict(id=identity,cells=len(rows),bytes=len(raw),sha256=sha(raw),
            cell_bounds=[[min(c[i] for c in rows) for i in range(3)],[max(c[i] for c in rows)+1 for i in range(3)]]))
    for key in sorted(groups):split(groups[key])
    doc=dict(profile=PROFILE,publication_id=record['id'],model_id=model.manifest['id'],**owned(record),
        model_manifest_sha256=sha(files['model.json']),source_model_sha256=record['source_model_sha256'],
        source_agent_sha256=sha(agent),canonical_cells_sha256=sha(encoded(cells)),frame_id=model.manifest['frame_id'],
        resolution_m=model.resolution,total_cells=len(cells),max_tile_cells=MAX_TILE_CELLS,
        source_files={n:dict(sha256=sha(files[n]),bytes=len(files[n])) for n in ('publication.json','model.json')},
        partitions=partitions,coverage='surface_evidence_only',quality='unverified',robot_ready=False,
        layout='little_endian_int64_xyz',selection_rule='cell_center_in_half_open_aabb')
    PartitionIndex.model_validate(doc);source_binding(doc,files)
    # Independent reconstruction proves each original cell occurs in exactly one partition.
    rebuilt=sorted(tuple(map(int,c)) for p in partitions for c in np.frombuffer(files[p['id']+'.bin'],dtype='<i8').reshape(-1,3))
    if rebuilt!=cells:raise ValueError('partition_reconstruction_mismatch')
    files['index.json']=json.dumps(doc,sort_keys=True,separators=(',',':')).encode()
    if len(files['index.json'])>MAX_INDEX_BYTES or sum(map(len,files.values()))>MAX_BYTES:raise ValueError('partition_package_budget')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        for name,raw in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,raw)
    raw=output.getvalue()
    if len(raw)>MAX_BYTES:raise ValueError('partition_package_budget')
    return raw,dict(profile=PROFILE,publication_id=record['id'],**owned(record),sha256=sha(raw),bytes=len(raw),
        index_sha256=sha(files['index.json']),model_manifest_sha256=doc['model_manifest_sha256'],
        frame_id=doc['frame_id'],partitions=len(partitions),total_cells=len(cells),
        quality='unverified',robot_ready=False,coverage='surface_evidence_only',
        contents='surface_partitions_and_source_manifests',max_query_tiles=MAX_QUERY_TILES,max_query_cells=MAX_QUERY_CELLS)


class PartitionedPreview:
    def __init__(self,path,publication,index_sha256,space_id=None):
        self.path=Path(path);self.publication=publication;self.expected_index=index_sha256;self.space_id=space_id
        if not isinstance(index_sha256,str) or not re.fullmatch('[a-f0-9]{64}',index_sha256):raise ValueError('partition_expected_digest')
        self.last_read=[]
        with self._archive() as archive:self.doc=self._index(archive)

    def _archive(self):
        if self.path.stat().st_size>MAX_BYTES:raise ValueError('partition_package_budget')
        return zipfile.ZipFile(self.path)

    def _index(self,archive):
        infos=archive.infolist();names=[i.filename for i in infos]
        if (len(names)!=len(set(names)) or not 3<=len(names)<=MAX_TILES+3
                or any(i.flag_bits&1 or i.is_dir() or i.file_size<1 for i in infos)
                or sum(i.file_size for i in infos)>MAX_BYTES):raise ValueError('partition_archive_layout')
        if archive.getinfo('index.json').file_size>MAX_INDEX_BYTES:raise ValueError('partition_index_budget')
        raw=archive.read('index.json')
        if sha(raw)!=self.expected_index:raise ValueError('partition_index_changed')
        doc=PartitionIndex.model_validate_json(raw).model_dump(exclude_none=True)
        if doc['publication_id']!=self.publication or doc.get('space_id')!=self.space_id:raise ValueError('partition_expected_binding')
        expected={'index.json',*doc['source_files'],*(p['id']+'.bin' for p in doc['partitions'])}
        if set(names)!=expected:raise ValueError('partition_archive_members')
        for member in doc['partitions']:
            if archive.getinfo(member['id']+'.bin').file_size!=member['bytes']:raise ValueError('partition_member_size')
        files={n:self._read(archive,n,m) for n,m in doc['source_files'].items()}
        source_binding(doc,files)
        return doc

    def _read(self,archive,name,member):
        if archive.getinfo(name).file_size!=member['bytes']:raise ValueError('partition_member_size')
        raw=archive.read(name)
        if len(raw)!=member['bytes'] or sha(raw)!=member['sha256']:raise ValueError('partition_member_integrity')
        return raw

    def _cells(self,archive,tiles):
        for tile in tiles:
            raw=self._read(archive,tile['id']+'.bin',tile)
            cells=[tuple(map(int,r)) for r in np.frombuffer(raw,dtype='<i8').reshape(-1,3)]
            b=tile['cell_bounds']
            if cells!=sorted(set(cells)) or any(not all(b[0][i]<=c[i]<b[1][i] for i in range(3)) for c in cells):
                raise ValueError('partition_cell_binding')
            self.last_read.append(tile['id'])
            yield from cells

    def _binding(self,doc):
        return dict(publication_id=doc['publication_id'],publication_model_manifest_sha256=doc['model_manifest_sha256'],
            source_model_sha256=doc['source_model_sha256'],model_id=doc['model_id'],index_sha256=self.expected_index,
            **owned(doc),quality='unverified',robot_ready=False)

    def query_range(self,bounds_m,frame_id,limit=DEFAULT_RANGE_CELLS):
        self.last_read=[]
        with self._archive() as archive:
            doc=self._index(archive)
            lo,hi,imin,imax=range_indices(doc['resolution_m'],bounds_m,frame_id,doc['frame_id'],limit)
            tiles=[p for p in doc['partitions'] if intersects(p['cell_bounds'],[imin,imax])]
            if len(tiles)>MAX_QUERY_TILES or sum(p['cells'] for p in tiles)>MAX_QUERY_CELLS:
                return dict(profile='cospace.partitioned-range/0.1',**self._binding(doc),bounds_m=[lo,hi],frame_id=frame_id,
                    resolution_m=doc['resolution_m'],unit='m',limit=limit,selection_rule=doc['selection_rule'],
                    status='partition_budget_exceeded',result_complete=False,matched_cells=None,returned_cells=0,
                    cell_indices=[],unlisted_state=None,coverage='surface_evidence_only',action='shrink_bounds',
                    partition_read=dict(matched=len(tiles),read=0,verified_cells=0,total=len(doc['partitions']),
                        max_tiles=MAX_QUERY_TILES,max_cells=MAX_QUERY_CELLS,scope='requested_partitions_only'))
            result=surface_range(self._cells(archive,tiles),doc['resolution_m'],bounds_m,frame_id,doc['frame_id'],limit)
            return dict(result,profile='cospace.partitioned-range/0.1',**self._binding(doc),
                partition_read=dict(matched=len(tiles),read=len(self.last_read),verified_cells=sum(p['cells'] for p in tiles),
                    total=len(doc['partitions']),max_tiles=MAX_QUERY_TILES,max_cells=MAX_QUERY_CELLS,scope='requested_partitions_only'))

    def query(self,point_m,frame_id):
        if (not isinstance(point_m,(tuple,list)) or len(point_m)!=3
                or any(type(v)not in (int,float) or abs(v)>1_000_000 or not math.isfinite(v) for v in point_m)):
            raise ValueError('invalid_point')
        self.last_read=[]
        with self._archive() as archive:
            doc=self._index(archive)
            if frame_id!=doc['frame_id']:raise ValueError('range_frame_mismatch')
            index=tuple(math.floor(v/doc['resolution_m']) for v in point_m)
            tiles=[p for p in doc['partitions'] if all(p['cell_bounds'][0][i]<=index[i]<p['cell_bounds'][1][i] for i in range(3))]
            present=index in set(self._cells(archive,tiles))
            return dict(profile='cospace.partitioned-query/0.1',**self._binding(doc),frame_id=frame_id,
                resolution_m=doc['resolution_m'],unit='m',
                point_m=list(point_m),cell_index=list(index),state='surface_candidate' if present else 'unknown',
                reason='observed_points_in_cell' if present else 'no_surface_evidence',
                coverage='surface_evidence_only',result_complete=True,
                partition_read=dict(read=len(self.last_read),total=len(doc['partitions']),scope='requested_partitions_only'))
