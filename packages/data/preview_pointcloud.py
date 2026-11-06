"""Bounded, explicitly declared PLY product intake. No coordinate inference."""
import json
import hashlib
import io
from pathlib import Path
import re
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from typing import Literal

FORMAT = 'ply_pointcloud'
MAX_POINTS = 1_000_000
MAX_BYTES = 32 * 1024 * 1024


class Coordinates(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    unit: Literal['m']
    frame_id: str = Field(pattern=r'^[A-Za-z0-9_/-]{1,100}$')
    axes: list[str] = Field(min_length=3, max_length=3)
    scope: Literal['sensor_local', 'scene_local']
    scene_alignment: Literal['unverified']


class Cloud(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    path: Literal['cloud.ply']
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: StrictInt = Field(gt=0, le=MAX_BYTES)
    points: StrictInt = Field(gt=0, le=MAX_POINTS)


class Provenance(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['derived_single_frame', 'existing_pointcloud']
    source_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_member_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    description: str = Field(min_length=1, max_length=500)


class Manifest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    profile: Literal['cospace.pointcloud-input/0.1']
    cloud: Cloud
    coordinates: Coordinates
    provenance: Provenance
    source_receipt_path: Literal['source.json'] | None = None


class SourceReceipt(BaseModel):
    """User declaration about the selected file, never an upstream acquisition log."""
    model_config = ConfigDict(extra='forbid', strict=True)
    profile: Literal['cospace.pointcloud-source/0.1']
    basis: Literal['user_declared_file']
    original_name: str = Field(min_length=1,max_length=160)
    cloud: Cloud
    coordinates: Coordinates
    description: str = Field(min_length=1,max_length=500)


def source_receipt(root,doc):
    if not doc.get('source_receipt_path'):return None
    path=Path(root)/doc['source_receipt_path']
    with path.open('rb') as stream:raw=stream.read(64_001)
    if len(raw)>64_000:raise ValueError('pointcloud_source_budget')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('pointcloud_source_duplicate_key')
            result[key]=value
        return result
    receipt=SourceReceipt.model_validate(json.loads(raw,object_pairs_hook=unique)).model_dump()
    name=receipt['original_name']
    provenance=doc['provenance']
    if (any(c in name for c in '/\\:') or any(ord(c)<32 for c in name) or not name.strip()
            or not receipt['description'].strip() or name in ('.','..')
            or receipt['cloud']!=doc['cloud'] or receipt['coordinates']!=doc['coordinates']
            or provenance['kind']!='existing_pointcloud' or provenance['description']!=receipt['description']
            or provenance['source_manifest_sha256']!=hashlib.sha256(raw).hexdigest()
            or provenance['source_member_sha256']!=doc['cloud']['sha256']):
        raise ValueError('pointcloud_source_binding_invalid')
    return receipt


def manifest(snapshot):
    root=Path(snapshot).resolve(); path=root/'pointcloud.json'
    with path.open('rb') as stream: raw=stream.read(64_001)
    if len(raw)>64_000:raise ValueError('pointcloud_manifest_budget')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('pointcloud_duplicate_key')
            result[key]=value
        return result
    try: doc=Manifest.model_validate(json.loads(raw,object_pairs_hook=unique)).model_dump(exclude_none=True)
    except (ValueError,TypeError) as exc:raise ValueError('pointcloud_declaration_invalid') from exc
    axes=doc['coordinates']['axes']
    if len(set(axes))!=3 or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}',v) for v in axes):
        raise ValueError('pointcloud_axes_invalid')
    source_receipt(root,doc)
    return doc,hashlib.sha256(raw).hexdigest()


def read_cloud(snapshot):
    root=Path(snapshot).resolve(); (doc,manifest_sha)=manifest(root); member=doc['cloud']; path=root/member['path']
    if not path.resolve().is_relative_to(root):raise ValueError('pointcloud_path_invalid')
    if path.stat().st_size!=member['bytes']:raise ValueError('pointcloud_integrity')
    with path.open('rb') as stream:raw=stream.read(member['bytes']+1)
    if len(raw)!=member['bytes'] or hashlib.sha256(raw).hexdigest()!=member['sha256']:
        raise ValueError('pointcloud_integrity')
    # One vertex element, float32 XYZ, optional uchar RGB, binary LE only.
    with io.BytesIO(raw) as stream:
        lines=[]; budget=0
        while True:
            line=stream.readline(1025);budget+=len(line)
            if not line or len(line)>1024 or budget>8192:raise ValueError('pointcloud_header_invalid')
            try:text=line.decode('ascii').rstrip('\r\n')
            except UnicodeDecodeError as exc:raise ValueError('pointcloud_header_invalid') from exc
            if text=='end_header':break
            if not text.startswith('comment '):lines.append(text)
        prefix=['ply','format binary_little_endian 1.0',f"element vertex {member['points']}",
                'property float x','property float y','property float z']
        rgb=['property uchar red','property uchar green','property uchar blue']
        if lines not in (prefix,prefix+rgb):raise ValueError('pointcloud_layout_unsupported')
        colored=lines==prefix+rgb
        dtype=np.dtype([(n,'<f4') for n in ('x','y','z')]+([(n,'u1') for n in ('red','green','blue')] if colored else []))
        expected=member['points']*dtype.itemsize
        if len(raw)-budget!=expected:raise ValueError('pointcloud_payload_size')
        payload=stream.read(expected+1)
        if len(payload)!=expected:raise ValueError('pointcloud_payload_size')
    values=np.frombuffer(payload,dtype=dtype)
    points=np.column_stack([values[n] for n in ('x','y','z')]).astype(np.float32)
    # Bound coordinate magnitudes for safe downstream 0.1m integer cell indexing.
    if not np.isfinite(points).all() or np.abs(points).max()>1_000_000:raise ValueError('pointcloud_coordinates_invalid')
    colors=np.column_stack([values[n] for n in ('red','green','blue')]) if colored else np.full(points.shape,160,dtype=np.uint8)
    checked={'snapshot_sha256':manifest_sha,'cloud_sha256':member['sha256'],
             'cloud_bytes':member['bytes'],'point_count':len(points),'input_frames':1,'used_frames':1,
             **doc['coordinates'],'appearance':'source_rgb' if colored else 'neutral_not_rgb'}
    return checked,points,colors,doc
