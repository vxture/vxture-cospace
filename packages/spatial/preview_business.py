"""Fixed local asset records and object links, separate from ontology properties."""
import hashlib
import json
from copy import deepcopy
from typing import Literal
from pydantic import Field,model_validator
from packages.spatial.preview_objects import Fixed
from packages.lifecycle.preview_scope import match,owned


class AssetFields(Fixed):
    asset_code:str=Field(default='',max_length=100)
    manufacturer:str=Field(default='',max_length=100)
    model:str=Field(default='',max_length=100)
    serial_number:str=Field(default='',max_length=100)


class LedgerDraft(Fixed):
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    source_system:str=Field(min_length=1,max_length=80)
    external_id:str=Field(min_length=1,max_length=100)
    version:str=Field(min_length=1,max_length=40)
    title:str=Field(min_length=1,max_length=100)
    fields:AssetFields=Field(default_factory=AssetFields)

    @model_validator(mode='after')
    def nonblank(self):
        if any(not getattr(self,k).strip() for k in ('source_system','external_id','version','title')):
            raise ValueError('ledger_required_text_blank')
        return self


class LedgerRecord(LedgerDraft):
    profile:Literal['cospace.preview-ledger/0.1']
    record_id:str=Field(pattern=r'^ledger-[a-f0-9]{16}$')
    project_id:str=Field(pattern=r'^project-[a-f0-9]{16}$')
    created_at:str=Field(min_length=1,max_length=80)
    confirmation:Literal['unverified']


class LedgerRef(Fixed):
    record_id:str=Field(pattern=r'^ledger-[a-f0-9]{16}$')
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


class BusinessBinding(Fixed):
    object_id:str=Field(min_length=1,max_length=160,pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$')
    ledger_ref:LedgerRef


class BusinessRequest(Fixed):
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    base_candidate_id:str=Field(min_length=1,max_length=100)
    base_manifest_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    bindings:list[BusinessBinding]=Field(max_length=100)


class FrozenRecord(Fixed):
    ref:LedgerRef
    record:LedgerRecord


class BusinessSnapshot(Fixed):
    profile:Literal['cospace.preview-business/0.1']
    model_id:str=Field(pattern=r'^build-[a-f0-9]{16}$')
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    project_id:str=Field(pattern=r'^project-[a-f0-9]{16}$')
    objects_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    bindings:list[BusinessBinding]=Field(max_length=100)
    records:list[FrozenRecord]=Field(max_length=100)
    confirmation:Literal['unverified']


def record_bytes(record):
    return json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def record_sha(record):return hashlib.sha256(record_bytes(record)).hexdigest()


def business_snapshot(manifest,objects,raw):
    doc=BusinessSnapshot.model_validate(json.loads(raw)).model_dump()
    declaration=manifest.get('business_association',{})
    if (objects is None or declaration.get('path')!='business.json'
            or declaration.get('binding_count')!=len(doc['bindings'])
            or doc['model_id']!=manifest['id'] or doc['objects_sha256']!=manifest['members']['objects.json']['sha256']):
        raise ValueError('business_snapshot_binding')
    match(doc,owned(manifest))
    member=manifest['members'].get('business.json',{})
    if member.get('sha256')!=hashlib.sha256(raw).hexdigest() or member.get('bytes')!=len(raw):
        raise ValueError('business_snapshot_integrity')
    object_ids={obj['object_id'] for obj in objects['objects']};seen=set();refs={}
    for value in doc['records']:
        ref=value['ref'];record=value['record'];identity=ref['record_id']
        if identity in refs or identity!=record['record_id'] or ref['sha256']!=record_sha(record):
            raise ValueError('business_record_binding')
        match(record,owned(manifest));refs[identity]=ref
    used=set()
    for binding in doc['bindings']:
        identity=binding['object_id'];ref=binding['ledger_ref']
        if identity in seen or identity not in object_ids or refs.get(ref['record_id'])!=ref:
            raise ValueError('business_object_binding')
        seen.add(identity);used.add(ref['record_id'])
    if used!=set(refs):raise ValueError('business_records_unreferenced')
    return doc


def links_for(doc,object_id):
    if doc is None:return []
    records={r['ref']['record_id']:r for r in doc['records']}
    return [deepcopy(records[b['ledger_ref']['record_id']]) for b in doc['bindings'] if b['object_id']==object_id]
