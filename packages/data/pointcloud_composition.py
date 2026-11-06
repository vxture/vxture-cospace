"""Bounded provenance for a PLY derived from multiple scene sources."""
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from packages.data.preview_pointcloud import Cloud, Coordinates


class CompositionSource(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=160)
    sha256: str = Field(pattern='^[a-f0-9]{64}$')
    source_points: StrictInt = Field(gt=0, le=200_000_000)
    matched_points: StrictInt = Field(ge=0, le=200_000_000)


class Composition(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    profile: Literal['cospace.pointcloud-composition/0.1']
    scene_manifest_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    sources: list[CompositionSource] = Field(min_length=1, max_length=32)
    origin: list[float] = Field(min_length=3, max_length=3)
    bounds_local: list[list[float]] = Field(min_length=2, max_length=2)
    unit_basis: Literal['assumed_metre_for_flow_validation', 'verified_metre']
    voxel_size: float = Field(ge=0, le=100)
    selection_method: Literal['all_points', 'first_source_then_lowest_ordinal_per_voxel']
    matched_points: StrictInt = Field(gt=0)
    retained_points: StrictInt = Field(gt=0, le=1_000_000)
    alignment_verified: Literal[False]
    cloud: Cloud
    coordinates: Coordinates
    description: str = Field(min_length=1, max_length=500)


def source_set_digest(sources):
    records = [{k: s[k] for k in ('name', 'sha256')} for s in sources]
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_composition(root, doc):
    if not doc.get('composition_path'):
        return None
    path = Path(root)/doc['composition_path']
    with path.open('rb') as stream:
        raw = stream.read(64_001)
    if len(raw) > 64_000:
        raise ValueError('composition_budget')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('composition_duplicate_key')
            value[key] = item
        return value
    value = Composition.model_validate(json.loads(raw, object_pairs_hook=unique)).model_dump()
    names = [s['name'] for s in value['sources']]
    bounds = value['bounds_local']
    provenance = doc['provenance']
    if (len(set(names)) != len(names)
            or any(any(c in n for c in '/\\:') or any(ord(c) < 32 for c in n) for n in names)
            or any(s['matched_points'] > s['source_points'] for s in value['sources'])
            or any(len(row) != 3 for row in bounds)
            or any(bounds[0][i] >= bounds[1][i] for i in range(3))
            or value['matched_points'] != sum(s['matched_points'] for s in value['sources'])
            or value['retained_points'] > value['matched_points']
            or value['retained_points'] != doc['cloud']['points']
            or (value['voxel_size'] == 0) != (value['selection_method'] == 'all_points')
            or value['voxel_size'] == 0 and value['matched_points'] != value['retained_points']
            or value['cloud'] != doc['cloud'] or value['coordinates'] != doc['coordinates']
            or value['coordinates']['scope'] != 'scene_local' or doc.get('source_receipt_path')
            or provenance['kind'] != 'existing_pointcloud'
            or provenance['description'] != value['description']
            or provenance['source_manifest_sha256'] != hashlib.sha256(raw).hexdigest()
            or provenance['source_member_sha256'] != source_set_digest(value['sources'])):
        raise ValueError('composition_binding_invalid')
    return value
