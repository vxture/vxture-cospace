"""Authorized metadata projection; never poll workers, load geometry or export files."""
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from packages.data.scene_attachments import SceneAttachments, checked_path
from packages.data.input_descriptions import InputDescriptions, DescriptionUnavailable
from packages.data.preflight_records import PreflightRecords, PreflightUnavailable
from packages.lifecycle.preview_scope import match

MAX_RECORDS = 10000
MAX_METADATA_BYTES = 262144


class CatalogUnavailable(RuntimeError):
    pass


class CatalogQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    space_id: str | None = Field(default=None, pattern=r'^space-[a-f0-9]{16}$')
    category: Literal['all', 'original', 'process', 'result'] = 'all'
    search: str = Field(default='', max_length=100)
    offset: int = Field(default=0, ge=0, le=MAX_RECORDS)
    limit: int = Field(default=50, ge=1, le=100)


def metadata(root, path, *, with_digest=False):
    checked_path(root, path)
    with path.open('rb') as stream:
        raw = stream.read(MAX_METADATA_BYTES + 1)
    if len(raw) > MAX_METADATA_BYTES:
        raise ValueError('metadata_budget')
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise ValueError('metadata_invalid')
    return (record, hashlib.sha256(raw).hexdigest()) if with_digest else record


def catalog(jobs, directory, policy, principal, query):
    # Derive scope from this request's verified principal/policy, never from a
    # browser-supplied workspace, a last-scene setting or preview visibility.
    if query.space_id:
        policy.require(principal, query.space_id, 'data.manage')
    spaces = {s['id']: s for s in directory.list('space')
              if 'data.manage' in policy.capabilities(principal, s['id'])
              and (not query.space_id or s['id'] == query.space_id)}
    if query.space_id and query.space_id not in spaces:
        raise PermissionError('space_access_denied')
    items, issues = [], []
    scanned = 0

    def issue(source, space=None):
        value = {'source': source, 'space_id': space, 'code': 'metadata_unavailable'}
        if value not in issues:
            issues.append(value)

    def add(record, kind, category, label, state, route, **values):
        if len(items) >= MAX_RECORDS:
            raise CatalogUnavailable('catalog_budget_exceeded')
        space = record['space_id']
        identity = record['id']
        label = label[:200] if isinstance(label, str) else identity
        created = record.get('created_at')
        created = created if isinstance(created, str) and len(created) <= 80 else None
        items.append({'key': f'{space}/{kind}:{identity}', 'record_id': identity,
                      'space_id': space, 'space_name': spaces[space]['name'],
                      'category': category, 'kind': kind, 'label': label,
                      'state': state, 'created_at': created,
                      'integrity': 'metadata_only',
                      'href': '#' + route + '?' + urlencode({'space': space, **values})})

    def scan(root, pattern, source):
        nonlocal scanned
        if root is None or not spaces:
            return
        for path in root.glob(pattern):
            scanned += 1
            if scanned > MAX_RECORDS:
                raise CatalogUnavailable('catalog_budget_exceeded')
            if path.parent.name.startswith('.'):
                continue
            try:
                record = metadata(root, path)
            except (OSError, ValueError, TypeError):
                # Ownership cannot be established; no ID/path/count is exposed.
                issue(source)
                continue
            identity = record.get('space_id')
            space = spaces.get(identity) if isinstance(identity, str) else None
            if not space:
                continue
            try:
                match(record, {'space_id': space['id'], 'project_id': space['project_id']})
                identity = path.stem if source == 'inputs' else path.parent.name
                pattern = {'inputs': r'input-[a-f0-9]{16}', 'jobs': r'build-[A-Za-z0-9-]+',
                           'publications': r'preview-[a-f0-9]{16}'}[source]
                if record.get('id') != identity or not re.fullmatch(pattern, identity):
                    raise ValueError('record_identity_invalid')
            except (ValueError, KeyError, TypeError):
                issue(source, space['id'])
                continue
            yield record

    if spaces and jobs.inputs is None:
        issue('inputs')
    for record in scan(jobs.inputs.root if jobs.inputs else None, 'input-*.json', 'inputs'):
        try:
            presentation = InputDescriptions(jobs.inputs).presentation(record)
            add(record, 'input', 'original', presentation['display_name'], 'registered',
                'data', tab='inputs', input=record['id'])
        except (OSError, ValueError, KeyError, TypeError, DescriptionUnavailable):
            issue('inputs', record['space_id'])
        try:
            check = PreflightRecords(jobs.inputs).latest(record['id'])
            if check:
                # Sequence locates saved evidence; it is not a new check or a
                # claim about the current files. The detail page rechecks scope.
                add(record | {'id': record['id'] + '@' + str(check['sequence'])},
                    'preflight', 'process', record.get('label', record['id']),
                    check['status'] if check['registration_matches'] else 'registration_changed',
                    'data', tab='inputs', input=record['id'], check=str(check['sequence']))
        except (OSError, ValueError, TypeError, KeyError, PreflightUnavailable):
            issue('preflight', record['space_id'])

    for record in scan(jobs.root, '*/job.json', 'jobs'):
        space = record['space_id']
        if 'build.run' in policy.capabilities(principal, space):
            # Failed/queued/running tasks are process records, never candidates.
            state = record.get('state')
            state = state if isinstance(state, str) and state in ('queued','running','succeeded','failed','interrupted','views_failed') else 'unknown'
            add(record, 'job', 'process', record['id'], state,
                'build', tab='tasks', job=record['id'])
        if record.get('state') == 'succeeded':
            add(record, 'candidate', 'result', record['id'], 'candidate_recorded',
                'data', tab='versions', artifact='candidate:' + record['id'])
            try:
                model = metadata(jobs.root, jobs.root / record['id'] / 'output' / 'model.json')
                match(model, {'space_id': space, 'project_id': record['project_id']})
                if model.get('id') != record['id']:
                    raise ValueError('model_identity_invalid')
                for kind in ('human_view', 'agent_view'):
                    if isinstance(model.get(kind), dict):
                        add(record, kind, 'result', record['id'], 'view_declared', 'data',
                            tab='versions', artifact='candidate:' + record['id'])
            except (OSError, ValueError, TypeError, KeyError):
                issue('views', space)

    for record in scan(jobs.root / 'publications', '*/publication.json', 'publications'):
        if 'space.preview' in policy.capabilities(principal, record['space_id']):
            add(record, 'publication', 'result', record['id'], 'publication_recorded',
                'delivery', publication=record['id'])
            if 'space.export' in policy.capabilities(principal, record['space_id']):
                add(record, 'offline_package', 'result', record['id'], 'export_on_request',
                    'delivery', publication=record['id'])

    for space in spaces:
        if jobs.batches is not None:
            try:
                for record in jobs.batches.list(space):
                    add(record, 'batch', 'process', record['name'], record['state'],
                        'data', tab='batches', batch=record['id'])
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                issue('batches', space)
        if jobs.inputs:
            try:
                for record in SceneAttachments(jobs.inputs).list(space):
                    add(record, 'attachment', 'original', record['name'], 'stored_original',
                        'data', tab='references')
            except (OSError, ValueError, TypeError, KeyError):
                issue('attachments', space)

    search = query.search.strip().casefold()
    items = [i for i in items if search in (i['label'] + ' ' + i['record_id'] + ' ' + i['space_name']).casefold()]
    counts = {category: sum(i['category'] == category for i in items) for category in ('original', 'process', 'result')}
    filtered = sorted((i for i in items if query.category == 'all' or i['category'] == query.category),
                      key=lambda i: i['key'])
    total = len(filtered)
    return {'profile': 'cospace.workspace-data-catalog/0.1', 'workspace_id': principal.workspace_id,
            'space_id': query.space_id, 'observed_at': datetime.now(timezone.utc).isoformat(),
            'status': 'partial' if issues else 'ready', 'issues': issues,
            'spaces': [{'id': s['id'], 'name': s['name']} for s in sorted(spaces.values(), key=lambda s: s['id'])],
            'items': filtered[query.offset:query.offset + query.limit], 'counts': counts, 'total': total,
            'offset': query.offset, 'limit': query.limit,
            'next_offset': query.offset + query.limit if query.offset + query.limit < total else None,
            'consistency': 'request_time_metadata_reads_not_transactional',
            'source_files_rechecked': False, 'consumer_state_checked': False,
            'delivery_history': 'not_recorded', 'quality': 'unverified'}
