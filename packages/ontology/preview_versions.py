"""Immutable local rule versions and diagnostic-only draft validation."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
import uuid
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

SCHEMA=Path(__file__).resolve().parents[2]/'contracts/schemas/preview-ontology-v0.1.schema.json'
MAX_BYTES=64*1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def definition(raw):
    if len(raw)>MAX_BYTES: raise ValueError('ontology_definition_too_large')
    try:
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError('ontology_definition_invalid')
        schema=SCHEMA.with_name('preview-ontology-v0.2.schema.json') if value.get('profile')=='cospace.preview-ontology/0.2' else SCHEMA
        Draft202012Validator(json.loads(schema.read_bytes())).validate(value)
        for kind in value['types'].values():
            for rule in kind['properties'].values():
                if rule['min_length']>rule['max_length']: raise ValueError('ontology_definition_invalid')
        for rule in value.get('relations',{}).values():
            if any(t not in value['types'] for t in rule['source_types']+rule['target_types']):raise ValueError('ontology_relation_type_undefined')
            if rule['symmetric'] and set(rule['source_types'])!=set(rule['target_types']):raise ValueError('ontology_symmetric_types_mismatch')
    except (ValueError,KeyError,TypeError,ValidationError) as exc:
        raise ValueError('ontology_definition_invalid') from exc
    return value


class PreviewOntologies:
    def __init__(self,root):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.lock=Lock()

    def path(self,identity,version):
        if (not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',identity)
                or not re.fullmatch(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}',version)):
            raise ValueError('ontology_not_found')
        target=self.root/identity/version
        if not target.resolve().is_relative_to(self.root): raise ValueError('ontology_not_found')
        return target

    def register(self,source):
        with Path(source).open('rb') as stream: raw=stream.read(MAX_BYTES+1)
        return self.register_bytes(raw)

    def register_bytes(self,raw,audit=None):
        value=definition(raw); target=self.path(value['ontology_id'],value['version'])
        with self.lock:
            if target.exists():
                record,_=self.read(value['ontology_id'],value['version'])
                if record['sha256']!=digest(raw): raise ValueError('ontology_version_already_sealed')
                return record
            record={'profile':'cospace.preview-ontology-record/0.1',
                    'ontology_id':value['ontology_id'],'version':value['version'],
                    'sha256':digest(raw),'bytes':len(raw),'title':value['title'],
                    'type_count':len(value['types']),'state':'sealed_preview_rules',
                    'registered_at':datetime.now(timezone.utc).isoformat()}
            if value.get('relations'):record['relation_count']=len(value['relations'])
            if audit:record['authoring']=audit
            target.parent.mkdir(exist_ok=True)
            staging=self.root/('.pending-'+uuid.uuid4().hex); staging.mkdir()
            try:
                (staging/'definition.json').write_bytes(raw)
                (staging/'record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                staging.rename(target)
            finally:
                if staging.exists():
                    for file in ('definition.json','record.json'):
                        (staging/file).unlink(missing_ok=True)
                    staging.rmdir()
            return record

    def read(self,identity,version,expected_sha256=None):
        target=self.path(identity,version)
        if not target.is_dir(): raise ValueError('ontology_not_found')
        try:
            record=json.loads((target/'record.json').read_bytes())
            with (target/'definition.json').open('rb') as stream:raw=stream.read(MAX_BYTES+1)
        except (FileNotFoundError,ValueError) as exc: raise ValueError('ontology_integrity_changed') from exc
        if (not isinstance(record,dict) or record.get('profile')!='cospace.preview-ontology-record/0.1'
                or record.get('ontology_id')!=identity or record.get('version')!=version
                or record.get('sha256')!=digest(raw) or record.get('bytes')!=len(raw)):
            raise ValueError('ontology_integrity_changed')
        if expected_sha256 is not None and expected_sha256!=record['sha256']:
            raise ValueError('ontology_reference_mismatch')
        value=definition(raw)
        if (value['ontology_id']!=identity or value['version']!=version
                or value['title']!=record.get('title') or len(value['types'])!=record.get('type_count')
                or len(value.get('relations',{}))!=record.get('relation_count',0)):
            raise ValueError('ontology_integrity_changed')
        return record,value

    def list(self):
        return [self.read(p.parent.parent.name,p.parent.name)[0]
                for p in sorted(self.root.glob('*/*/record.json'))]

    def inspect(self,identity,version,sha256,objects):
        record,value=self.read(identity,version,sha256)
        return inspect_objects(record,value,objects)


def inspect_objects(record,value,objects):
    if not isinstance(objects,list) or not 1<=len(objects)<=100:
        raise ValueError('invalid_object_batch')
    issues=[]; seen=set()
    def issue(code,path,obj,message):
        issues.append({'code':code,'path':path,'object_id':obj.get('object_id') if isinstance(obj.get('object_id'),str) else None,
                       'message':message})
    def pointer(key): return str(key).replace('~','~0').replace('/','~1')
    for index,obj in enumerate(objects):
        base=f'/objects/{index}'
        if not isinstance(obj,dict):
            issue('invalid_object',base,{},'对象必须是JSON对象。'); continue
        for key in obj.keys()-{'object_id','type_id','properties'}:
            issue('undefined_object_field',base+'/'+pointer(key),obj,'草稿校验不接受该字段。')
        identity=obj.get('object_id')
        if not isinstance(identity,str) or not identity.strip() or len(identity)>160:
            issue('invalid_object_id',base+'/object_id',obj,'对象ID必须是1至160字的非空字符串。')
        elif identity in seen:
            issue('duplicate_object_id',base+'/object_id',obj,'本批对象ID重复。')
        else: seen.add(identity)
        type_id=obj.get('type_id')
        kind=value['types'].get(type_id) if isinstance(type_id,str) else None
        if kind is None:
            issue('unknown_type',base+'/type_id',obj,'类型未在所选本体版本中定义；需人工确认。')
        properties=obj.get('properties')
        if not isinstance(properties,dict):
            issue('invalid_properties',base+'/properties',obj,'属性必须是JSON对象。'); continue
        if kind is None: continue
        for key in properties.keys()-kind['properties'].keys():
            issue('undefined_property',base+'/properties/'+pointer(key),obj,'属性未在该类型中定义。')
        for key,rule in kind['properties'].items():
            path=base+'/properties/'+pointer(key)
            if key not in properties:
                if rule['required']: issue('missing_required_property',path,obj,'缺少必填属性。')
            elif not isinstance(properties[key],str):
                issue('invalid_property_type',path,obj,'属性值必须是字符串。')
            elif (not rule['min_length']<=len(properties[key])<=rule['max_length']
                    or rule['min_length']>0 and not properties[key].strip()):
                issue('invalid_property_length',path,obj,f"属性长度应为{rule['min_length']}至{rule['max_length']}字，非空属性不可仅含空白。")
    return {'profile':'cospace.preview-ontology-validation/0.1',
            'ontology_ref':{k:record[k] for k in ('ontology_id','version','sha256')},
            'checked_at':datetime.now(timezone.utc).isoformat(),
            'status':'failed' if issues else 'passed','object_count':len(objects),'issues':issues,
            'saved':False,'semantic_confirmation':'not_attempted','robot_ready':False,
            'scope':'draft_rules_only'}
