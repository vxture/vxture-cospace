"""Read saved scene descriptors without polling jobs or opening model arrays.

These are registration/task facts, not a fresh artifact-integrity acceptance.
"""
import hashlib
import json
import re

from packages.lifecycle.preview_scope import scope, match


def overview(jobs, space_id):
    ownership = scope(jobs.directory, space_id)
    selection_path = jobs.root / 'space-selections' / (space_id + '.json')
    before = selection_path.read_bytes() if selection_path.exists() else None
    selection = json.loads(before) if before else None
    result = {'space_id': space_id, 'candidate_ref': None, 'job': None, 'stages': None,
              'counts': None, 'basis': 'saved_metadata', 'jobs_polled': False,
              'artifact_members_verified': False}
    if selection:
        match(selection, ownership)
        identity = selection['candidate_id']
        if not re.fullmatch(r'build-[A-Za-z0-9-]+', identity):
            raise ValueError('overview_candidate_invalid')
        record = json.loads((jobs.root / identity / 'job.json').read_bytes())
        if record['id'] != identity:
            raise ValueError('overview_job_mismatch')
        match(record, ownership)
        result['candidate_ref'] = {'candidate_id': identity}
        raw = (jobs.root / identity / 'output/model.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != selection['model_manifest_sha256']:
            raise ValueError('overview_selection_changed')
        manifest = json.loads(raw)
        match(manifest, ownership)
        result['counts'] = {name: manifest.get(section, {}).get(field, 0) for name, section, field in (
            ('objects', 'semantic_annotation', 'object_count'),
            ('business_bindings', 'business_association', 'binding_count'),
            ('object_relations', 'object_relations', 'relation_count'))}
        if any(type(n) is not int or n < 0 for n in result['counts'].values()):
            raise ValueError('overview_counts_invalid')
    else:
        # Read only this scene's saved task headers; jobs.list() polls processes.
        records = []
        for path in jobs.root.glob('*/job.json'):
            item = json.loads(path.read_bytes())
            if item.get('space_id') == space_id:
                match(item, ownership)
                records.append(item)
        record = max(records, key=lambda item: (item.get('created_at', ''), item['id'])) if records else None
    if record:
        fields = ('id', 'space_id', 'created_at', 'state', 'display_code', 'build_code',
                  'input_id', 'mode', 'pipeline', 'view_parent_id')
        result['job'] = {k: record[k] for k in fields if k in record}
        if record.get('input_binding'):
            result['job']['input_binding'] = {k: record['input_binding'][k] for k in ('label', 'format') if k in record['input_binding']}
        views = {}
        for kind, ref in record.get('view_tasks', {}).items():
            if kind not in ('human', 'agent'):
                continue
            _, task = jobs.split.task(ref)
            match(task, ownership)
            if task['view_kind'] != kind or task['frozen_model'] != record.get('frozen_model'):
                raise ValueError('overview_view_mismatch')
            views[kind] = {'state': task['state']}
        result['stages'] = {'space_id': space_id, 'job_id': record['id'], 'views': views,
                            'legacy': not bool(record.get('pipeline'))}
    if (selection_path.read_bytes() if selection_path.exists() else None) != before:
        raise ValueError('overview_selection_changed')
    return result
