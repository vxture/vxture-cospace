"""F06b synthetic candidate construction. No release mutation or quality reuse."""
import copy
import hashlib
import json
import math
import re
import threading
from pathlib import Path

from jsonschema import Draft202012Validator

from packages.service.release_contract import inspect_release_snapshot
from packages.service.sample import read_json

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/schemas/spatial-change-v0.1.schema.json'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def object_digest(obj):
    """Hash normalized supported object fields; IDs plus outer base pin prevent replay."""
    return digest(canonical(obj))


def build_candidate(source, change, resources, *, now):
    source = dict(source)
    change = copy.deepcopy(change)
    resources = dict(resources)
    schema=json.loads(SCHEMA.read_text(encoding='utf-8'))
    if list(Draft202012Validator(schema).iter_errors(change)):
        raise ValueError('change_structure')
    if len(resources)>32 or any(type(raw) is not bytes or len(raw)>8388608 for raw in resources.values()):
        raise ValueError('resource_budget')
    if sum(map(len,resources.values()))>33554432:
        raise ValueError('resource_budget')
    for path in resources:
        if (not isinstance(path,str) or not path or '\\' in path or re.search(r'[:\x00-\x1f]',path)
                or any(p in ('','.','..') or p.endswith((' ','.')) for p in path.split('/'))):
            raise ValueError('unsafe_resource_path')
    if len({p.casefold() for p in resources})!=len(resources):
        raise ValueError('resource_path_collision')
    report=inspect_release_snapshot(source,now=now)
    release=read_json(source['release.json'])
    truth=read_json(source[release['source_truth']['path']])
    expected={'release_id':release['id'],'release_sha256':report['release_sha256'],
              'truth_id':truth['id'],'truth_sha256':release['source_truth']['sha256']}
    if change['base']!=expected or change['scene_id']!=release['scene_id']:
        raise ValueError('base_conflict')
    existing_ids = set()
    for raw in source.values():
        try:
            document=read_json(raw)
        except ValueError:
            continue
        if isinstance(document,dict) and isinstance(document.get('id'),str):
            existing_ids.add(document['id'])
    new_ids=[change['new_truth_id'],change['new_objects_id'],change['change_id']]
    if len(set(new_ids))!=3 or set(new_ids)&existing_ids:
        raise ValueError('new_identity_conflict')
    objects=read_json(source[truth['objects']['path']])
    scope=read_json(source[truth['scope']['path']])
    ontology=read_json(source[truth['ontology']['path']])
    original={o['object_id']:o for o in objects['instances']}
    modified=copy.deepcopy(original)
    touched=set()
    roles=set()
    used=set()
    resource_ids=set(existing_ids)|set(new_ids)
    member_bindings={}

    def resource(ref):
        path=ref['path']
        if path not in resources:
            raise ValueError('resource_missing')
        raw=resources[path]
        if type(ref['bytes']) is not int or ref['bytes']!=len(raw) or digest(raw)!=ref['sha256']:
            raise ValueError('resource_integrity_mismatch')
        if path in member_bindings:
            raise ValueError('duplicate_resource_reference')
        if ref['id'] in resource_ids:
            raise ValueError('resource_identity_conflict')
        resource_ids.add(ref['id'])
        member_bindings[path]=ref
        used.add(path)
        return raw

    for ref in change['evidence']:
        resource(ref)
    for operation in change['operations']:
        op=operation['op']
        if op=='resource.replace':
            role=operation['role']
            if role in roles:
                raise ValueError('duplicate_resource_operation')
            roles.add(role)
            if operation['expected_sha256']!=truth[role]['sha256']:
                raise ValueError('resource_precondition_conflict')
            resource(operation['replacement'])
            if operation['replacement']['sha256']==truth[role]['sha256']:
                raise ValueError('no_op_resource_change')
            continue
        obj=operation.get('object')
        identity=obj['object_id'] if obj is not None else operation['object_id']
        if identity in touched:
            raise ValueError('duplicate_object_operation')
        touched.add(identity)
        if op=='object.add':
            if identity in original:
                raise ValueError('object_already_exists')
        else:
            if identity not in original or operation['expected_object_sha256']!=object_digest(original[identity]):
                raise ValueError('object_precondition_conflict')
        if op=='object.remove':
            del modified[identity]
        else:
            if obj['type_id'] not in ontology['type_ids']:
                raise ValueError('unknown_object_type')
            if any(type(x) not in (int,float) or not math.isfinite(x) for x in obj['anchor']):
                raise ValueError('nonfinite_anchor')
            if any(not a<=p<b for a,p,b in zip(scope['bounds'][0],obj['anchor'],scope['bounds'][1])):
                raise ValueError('object_anchor_out_of_scope')
            if op=='object.replace' and obj==original[identity]:
                raise ValueError('no_op_object_change')
            modified[identity]=obj
    if not modified:
        raise ValueError('empty_object_set_unsupported')
    if used!=set(resources):
        raise ValueError('unreferenced_resources')

    # Store candidate blobs by content digest: no input path ever becomes an output path.
    blobs={}
    def put(identity,raw):
        sha=digest(raw)
        path=f'blobs/{sha}'
        blobs[path]=raw
        return {'id':identity,'path':path,'sha256':sha,'bytes':len(raw)}
    change_ref=put(change['change_id'],canonical(change))
    objects['id']=change['new_objects_id']
    objects['instances']=[modified[k] for k in sorted(modified)]
    candidate_truth=copy.deepcopy(truth)
    candidate_truth['id']=change['new_truth_id']
    candidate_truth['kind']='candidate_content'
    candidate_truth['schema_version']='cospace.change-candidate/0.1'
    candidate_truth.pop('provenance')
    copied={}
    def copy_ref(ref):
        if ref['path'] not in copied:
            copied[ref['path']]=put(ref['id'],source[ref['path']])
        return copied[ref['path']]
    objects['ontology']=copy_ref(truth['ontology'])
    candidate_truth['objects']=put(objects['id'],canonical(objects))
    for key in ('frame','scope','ontology','geometry','coverage'):
        if key not in roles:
            candidate_truth[key]=copy_ref(truth[key])
    for operation in change['operations']:
        if operation['op']=='resource.replace':
            ref=operation['replacement']
            candidate_truth[operation['role']]=put(ref['id'],resources[ref['path']])
    evidence_refs=[put(ref['id'],resources[ref['path']]) for ref in change['evidence']]
    # Candidate provenance is deliberately not an adopted F04 provenance document.
    candidate={
        'schema_version':'cospace.change-candidate/0.1','candidate_id':change['new_truth_id'],
        'scene_id':change['scene_id'],'base':expected,'change':change_ref,
        'content':put(candidate_truth['id'],canonical(candidate_truth)),
        'evidence':evidence_refs,
        'required_rechecks':['independent_quality','coverage_partition','semantic_target_set','human_view_derivation','machine_view_derivation'],
        'impacted_views':sorted(report['view_ids']),'view_policy':'invalidate_all_no_reuse',
        'quality_status':'pending_independent_validation','publication_status':'candidate_only',
        'authorized':False,'real_release_ready':False}
    # Old provenance remains an external fixed baseline reference, never silently copied as new approval.
    candidate['base_provenance']=truth['provenance']
    result={'candidate':candidate,'blobs':blobs}
    validate_candidate(result)
    return result


def validate_candidate(result):
    """Recheck transport integrity and non-publication flags, not independent adoption."""
    candidate=result['candidate']
    if (candidate['schema_version']!='cospace.change-candidate/0.1'
            or candidate['publication_status']!='candidate_only'
            or candidate['quality_status']!='pending_independent_validation'
            or candidate['authorized'] is not False or candidate['real_release_ready'] is not False
            or candidate['view_policy']!='invalidate_all_no_reuse'):
        raise ValueError('candidate_status_invalid')
    refs=[candidate['change'],candidate['content'],*candidate['evidence']]
    content=read_json(result['blobs'][candidate['content']['path']])
    refs.extend(content[k] for k in ('frame','scope','ontology','objects','geometry','coverage'))
    seen=set()
    for ref in refs:
        raw=result['blobs'].get(ref['path'])
        if type(raw) is not bytes or len(raw)!=ref['bytes'] or digest(raw)!=ref['sha256']:
            raise ValueError('candidate_integrity_mismatch')
        seen.add(ref['path'])
    if set(result['blobs'])!=seen:
        raise ValueError('candidate_extra_blobs')
    if content['id']!=candidate['candidate_id'] or content['scene_id']!=candidate['scene_id']:
        raise ValueError('candidate_identity_mismatch')
    return True


class CandidateBranch:
    """Process-local CAS experiment, not persistent publication or distributed locking."""
    def __init__(self, release_sha256):
        self._base=release_sha256
        self._revision=0
        self._head=None
        self._lock=threading.Lock()

    def submit(self, result, *, expected_revision):
        result=copy.deepcopy(result)
        validate_candidate(result)
        with self._lock:
            if type(expected_revision) is not int or expected_revision!=self._revision:
                raise ValueError('candidate_revision_conflict')
            candidate=result['candidate']
            if candidate['base']['release_sha256']!=self._base:
                raise ValueError('candidate_base_conflict')
            self._head=copy.deepcopy(result)
            self._revision+=1
            return {'revision':self._revision,'candidate_id':candidate['candidate_id'],'published':False}

    def snapshot(self):
        with self._lock:
            return {'revision':self._revision,'head':copy.deepcopy(self._head)}
