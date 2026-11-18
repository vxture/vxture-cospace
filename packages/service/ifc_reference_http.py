"""Validated commands and path-free responses for scene IFC reference management."""
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from packages.data.ifc_structure_read import validate_structure
from packages.data.ifc_workspace import read_json


class TaskCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    space_id: str = Field(pattern='^space-[a-f0-9]{16}$')
    attachment_id: str = Field(pattern='^attachment-[a-f0-9]{16}$')
    retry: bool = False


class ActivateCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    space_id: str = Field(pattern='^space-[a-f0-9]{16}$')
    task_id: str = Field(pattern='^[a-f0-9]{64}$')
    expected_revision: int = Field(ge=0)


def public_listing(versions, space, can_manage):
    value = versions.listing(space)
    keys = ('id', 'name', 'actor', 'attachment_id', 'state', 'requested_at', 'finished_at',
            'catalog_sha256', 'error')
    tasks = [{k:t[k] for k in keys if k in t} for t in value['tasks'].values()
             if can_manage or t['id'] == value['current']]
    return {'profile':'cospace.ifc-reference/0.1', 'space_id':space, 'can_manage':can_manage,
            'revision':value['revision'], 'current':value['current'],
            'tasks':sorted(tasks, key=lambda t:(t['requested_at'], t['id']), reverse=True),
            'switches':value['switches'] if can_manage else []}


def preview_version(versions, space, task_id):
    task = versions.listing(space)['tasks'].get(task_id)
    if task is None or task['state'] != 'ready':
        raise ValueError('ifc_version_not_ready')
    binding = versions.resolve(space, catalog_sha256=task['catalog_sha256'], include_pending=True)
    _, doc = read_json(Path(binding.root)/'ifc.json', 8*1024*1024)
    entities, relations, products = validate_structure(doc)
    return {'space_id':space, 'task_id':task_id, 'catalog_sha256':binding.catalog_sha256,
            'assessment':'unverified', 'role_counts':dict(sorted(Counter(e.role for e in entities).items())),
            'entity_count':len(entities), 'relation_count':len(relations),
            'geometry_counts':doc['geometry_counts'],
            'sample':[{'name':products[e.entity_id]['name'], 'role':e.role, 'ifc_type':e.ifc_type}
                      for e in entities if e.role in ('level','door','stair')][:30]}
