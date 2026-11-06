"""Frozen object relation snapshots with fixed object and ontology bindings."""
from copy import deepcopy
import hashlib
import json
from typing import Literal
from pydantic import Field
from packages.spatial.preview_objects import Fixed,OntologyRef
from packages.lifecycle.preview_scope import match,owned
from packages.ontology.preview_relations import inspect_relations

ID=r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$'
class RelationDraft(Fixed):
    relation_id:str=Field(min_length=1,max_length=160,pattern=ID)
    type_id:str=Field(min_length=1,max_length=64)
    source_id:str=Field(min_length=1,max_length=160,pattern=ID)
    target_id:str=Field(min_length=1,max_length=160,pattern=ID)
    note:str=Field(min_length=1,max_length=500,pattern=r'\S')

class RelationRecord(RelationDraft):
    confirmation:Literal['unverified']

class RelationRequest(Fixed):
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    base_candidate_id:str=Field(min_length=1,max_length=100)
    base_manifest_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    ontology_ref:OntologyRef
    relations:list[RelationDraft]=Field(max_length=200)

class RelationSnapshot(Fixed):
    profile:Literal['cospace.preview-relations/0.1']
    model_id:str=Field(pattern=r'^build-[a-f0-9]{16}$')
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    project_id:str=Field(pattern=r'^project-[a-f0-9]{16}$')
    objects_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    ontology_ref:OntologyRef
    relations:list[RelationRecord]=Field(max_length=200)
    confirmation:Literal['unverified']

def relation_snapshot(manifest,objects,ontology,raw):
    doc=RelationSnapshot.model_validate(json.loads(raw)).model_dump()
    declaration=manifest.get('object_relations',{});member=manifest['members'].get('relations.json',{})
    if not isinstance(declaration,dict) or type(declaration.get('relation_count')) is not int:raise ValueError('relation_snapshot_binding')
    if (not objects or declaration.get('path')!='relations.json' or declaration.get('relation_count')!=len(doc['relations'])
        or doc['model_id']!=manifest['id'] or doc['ontology_ref']!=objects['ontology_ref']
        or doc['objects_sha256']!=manifest['members']['objects.json']['sha256']):raise ValueError('relation_snapshot_binding')
    match(doc,owned(manifest))
    if member.get('sha256')!=hashlib.sha256(raw).hexdigest() or member.get('bytes')!=len(raw):raise ValueError('relation_snapshot_integrity')
    if inspect_relations(ontology,objects['objects'],doc['relations'])['status']!='passed':raise ValueError('relation_rules_failed')
    # Even empty relation snapshots require a relation-capable fixed ontology.
    if not ontology.get('relations'):raise ValueError('ontology_relations_not_available')
    return doc

def relations_for(doc,object_id=None):
    if doc is None:return []
    return deepcopy([r for r in doc['relations'] if object_id is None or object_id in (r['source_id'],r['target_id'])])
