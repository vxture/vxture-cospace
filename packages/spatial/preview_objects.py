"""Fixed semantic snapshots: model-point evidence never confirms field meaning."""
import hashlib
import json
from copy import deepcopy
from typing import Any
from pathlib import Path
import numpy as np
from pydantic import BaseModel,ConfigDict,Field
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from packages.lifecycle.preview_scope import match,owned
from packages.ontology.preview_versions import definition,inspect_objects


class Fixed(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)


class OntologyRef(Fixed):
    ontology_id:str=Field(min_length=1,max_length=64)
    version:str=Field(min_length=1,max_length=20)
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


class ObjectDraft(Fixed):
    object_id:str=Field(min_length=1,max_length=160,pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$')
    type_id:str=Field(min_length=1,max_length=64)
    properties:dict[str,Any]=Field(max_length=32)
    point_index:int=Field(ge=0)


class SemanticRequest(Fixed):
    space_id:str=Field(min_length=1,max_length=100)
    base_candidate_id:str=Field(min_length=1,max_length=100)
    base_manifest_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    ontology_ref:OntologyRef
    objects:list[ObjectDraft]=Field(min_length=1,max_length=100)


def snapshot(manifest,objects_raw,ontology_raw,points=None):
    """Offline validates bindings; online additionally recomputes model-point anchors."""
    semantic=manifest.get('semantic_annotation')
    if not semantic: raise ValueError('semantic_objects_not_available')
    for name,raw in [('objects.json',objects_raw),('ontology.json',ontology_raw)]:
        member=manifest['members'].get(name,{})
        if member.get('sha256')!=hashlib.sha256(raw).hexdigest() or member.get('bytes')!=len(raw):
            raise ValueError('semantic_snapshot_integrity')
    doc=json.loads(objects_raw); ontology=definition(ontology_raw)
    if not isinstance(doc,dict):raise ValueError('invalid_semantic_objects')
    schema=Path(__file__).resolve().parents[2]/'contracts/schemas/preview-objects-v0.1.schema.json'
    try:Draft202012Validator(json.loads(schema.read_bytes())).validate(doc)
    except ValidationError as exc:raise ValueError('invalid_semantic_snapshot') from exc
    ref={k:ontology[k] for k in ('ontology_id','version')}
    ref['sha256']=hashlib.sha256(ontology_raw).hexdigest()
    if (doc.get('profile')!='cospace.preview-objects/0.1'
            or semantic.get('objects_path')!='objects.json' or semantic.get('ontology_path')!='ontology.json'
            or doc.get('ontology_ref')!=ref or semantic.get('ontology_ref')!=ref
            or doc.get('source_model_sha256')!=manifest['members']['spatial.npz']['sha256']
            or doc.get('model_id')!=manifest['id'] or doc.get('frame_id')!=manifest['frame_id']
            or doc.get('unit')!='m' or doc.get('annotation_id')!=semantic.get('annotation_id')
            or doc.get('base_candidate_ref')!=semantic.get('base_candidate_ref')):
        raise ValueError('semantic_snapshot_binding')
    match(doc,owned(manifest))
    for view in ('human_view','agent_view'):
        if (manifest.get(view,{}).get('objects_path')!='objects.json'
                or manifest[view].get('ontology_ref')!=ref
                or manifest[view].get('source_model_sha256')!=doc['source_model_sha256']):
            raise ValueError('semantic_view_binding')
    objects=doc.get('objects')
    if not isinstance(objects,list) or not 1<=len(objects)<=100 or semantic.get('object_count')!=len(objects):
        raise ValueError('invalid_semantic_objects')
    drafts=[]
    for obj in objects:
        if (not isinstance(obj,dict) or set(obj)!={'object_id','type_id','properties','anchor_m','evidence','confirmation'}
                or obj['confirmation']!='unverified'):
            raise ValueError('invalid_semantic_object')
        if (not isinstance(obj['anchor_m'],list) or len(obj['anchor_m'])!=3
                or any(type(v) not in (int,float) for v in obj['anchor_m'])):
            raise ValueError('invalid_object_anchor')
        anchor=np.asarray(obj['anchor_m'],dtype=float); evidence=obj['evidence']
        if (anchor.shape!=(3,) or not np.isfinite(anchor).all() or not isinstance(evidence,dict)
                or set(evidence)!={'kind','member','sha256','point_index'}
                or evidence['kind']!='model_point' or evidence['member']!='spatial.npz'
                or evidence['sha256']!=doc['source_model_sha256']
                or type(evidence['point_index']) is not int or evidence['point_index']<0):
            raise ValueError('invalid_object_evidence')
        if points is not None:
            index=evidence['point_index']
            if index>=len(points) or not np.allclose(anchor,points[index],rtol=0,atol=1e-6):
                raise ValueError('object_anchor_mismatch')
        drafts.append({k:obj[k] for k in ('object_id','type_id','properties')})
    report=inspect_objects(ref,ontology,drafts)
    if report['status']!='passed': raise ValueError('semantic_rules_failed')
    return doc


def object_result(manifest,doc,object_id=None):
    if doc is None: raise ValueError('semantic_objects_not_available')
    objects=doc['objects']
    if object_id is not None:
        objects=[obj for obj in objects if obj['object_id']==object_id]
        if not objects: raise ValueError('object_not_found')
    return {'profile':'cospace.preview-object-query/0.1','model_id':manifest['id'],
            'source_model_sha256':doc['source_model_sha256'],'frame_id':doc['frame_id'],'unit':'m',
            'annotation_id':doc['annotation_id'],'ontology_ref':deepcopy(doc['ontology_ref']),
            'objects':deepcopy(objects),'quality':'unverified','robot_ready':False,
            'evidence_scope':'frozen_model_points_not_independent_field_check',**owned(manifest)}
