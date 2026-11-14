"""Read saved scene descriptors without polling jobs or opening model arrays.

These are registration/task facts, not a fresh artifact-integrity acceptance.
"""
import hashlib
import json
import re

from packages.lifecycle.preview_scope import scope, match

JOB_FILE='job.json'


def _candidate(jobs,selection,ownership,observe):
    match(selection,ownership)
    identity=selection['candidate_id']
    if not re.fullmatch(r'build-[A-Za-z0-9-]+',identity):
        raise ValueError('overview_candidate_invalid')
    job_path=jobs.root/identity/JOB_FILE
    manifest_path=jobs.root/identity/'output/model.json'
    observe(job_path);observe(manifest_path)
    record=json.loads(job_path.read_bytes())
    if record['id']!=identity:raise ValueError('overview_job_mismatch')
    match(record,ownership)
    raw=manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=selection['model_manifest_sha256']:
        raise ValueError('overview_selection_changed')
    manifest=json.loads(raw);match(manifest,ownership)
    counts={name:manifest.get(section,{}).get(field,0) for name,section,field in (
        ('objects','semantic_annotation','object_count'),
        ('business_bindings','business_association','binding_count'),
        ('object_relations','object_relations','relation_count'))}
    if any(type(n) is not int or n<0 for n in counts.values()):
        raise ValueError('overview_counts_invalid')
    return record,counts


def _job_summary(record):
    fields=('id','space_id','created_at','state','display_code','build_code',
            'input_id','mode','pipeline','view_parent_id')
    result={k:record[k] for k in fields if k in record}
    if record.get('input_binding'):
        result['input_binding']={k:record['input_binding'][k] for k in ('label','format') if k in record['input_binding']}
    return result


def _stages(jobs,record,ownership,observe):
    views={}
    for kind,ref in record.get('view_tasks',{}).items():
        if kind not in ('human','agent'):continue
        observe(jobs.root/ref['job_id']/'views'/ref['task_id']/'task.json')
        _,task=jobs.split.task(ref)
        match(task,ownership)
        if task['view_kind']!=kind or task['frozen_model']!=record.get('frozen_model'):
            raise ValueError('overview_view_mismatch')
        views[kind]={'state':task['state']}
    return {'space_id':ownership['space_id'],'job_id':record['id'],'views':views,
            'legacy':not bool(record.get('pipeline'))}


def overview(jobs, space_id):
    # Read models never bypass ownership or HTTP ACL checks.
    ownership=scope(jobs.directory,space_id)
    cached=jobs.read_model.cached(space_id,ownership)
    if cached is not None and (cached.get('latest_job') or {}).get('id')==jobs.read_model.latest(space_id):return cached
    return _read(jobs,space_id)


def _read(jobs, space_id):
    ownership = scope(jobs.directory, space_id)
    selection_path = jobs.root / 'space-selections' / (space_id + '.json')
    dependencies={}
    def observe(path):
        dependencies.update(jobs.read_model.fingerprint([path]))
    observe(selection_path)
    latest=jobs.read_model.latest(space_id)
    latest_path=jobs.root/latest/JOB_FILE if latest else None
    if latest_path:observe(latest_path)
    latest_record=json.loads(latest_path.read_bytes()) if latest_path else None
    if latest_record:match(latest_record,ownership)
    before = selection_path.read_bytes() if selection_path.exists() else None
    selection = json.loads(before) if before else None
    result = {'space_id': space_id, 'candidate_ref': None, 'job': None, 'stages': None,
              'counts': None, 'basis': 'saved_metadata', 'jobs_polled': False,
              'artifact_members_verified': False}
    if selection:
        record,result['counts']=_candidate(jobs,selection,ownership,observe)
        result['candidate_ref']={'candidate_id':selection['candidate_id']}
    else:
        record=latest_record
    if record:
        result['job']=_job_summary(record)
        result['stages']=_stages(jobs,record,ownership,observe)
    if (selection_path.read_bytes() if selection_path.exists() else None) != before:
        raise ValueError('overview_selection_changed')
    result['latest_job']={k:latest_record[k] for k in ('id','space_id','created_at','state','display_code','build_code') if k in latest_record} if latest_record else None
    # Fixed-size scalar projection; dependency stamps invalidate file-backed changes.
    if jobs.read_model.fingerprint([jobs.root/name for name in dependencies])!=dependencies or jobs.read_model.latest(space_id)!=latest:
        raise ValueError('overview_sources_changed')
    jobs.read_model.save(space_id,dependencies,result,ownership)
    return result
