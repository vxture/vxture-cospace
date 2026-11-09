"""Bounded, metadata-only fixed-rule references in one authorized scene."""
from datetime import datetime, timezone
import re
from urllib.parse import urlencode
from pydantic import BaseModel, ConfigDict, Field
from packages.data.workspace_catalog import metadata
from packages.lifecycle.preview_scope import scope, match

MAX_RECORDS = 10000


class UsageQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    ontology_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    offset: int = Field(default=0, ge=0, le=MAX_RECORDS)
    limit: int = Field(default=20, ge=1, le=100)


def reference_model(root, path, kind, ownership, record):
    identity = path.parent.name
    model_path = path.parent/('output/model.json' if kind == 'candidate' else 'model.json')
    model, model_sha = metadata(root, model_path, with_digest=True)
    match(model, ownership)
    model_id = identity if kind == 'candidate' else record['candidate_id']
    if model.get('id') != model_id:
        raise ValueError('model_mismatch')
    if kind == 'publication' and model_sha != record.get('model_manifest_sha256'):
        raise ValueError('publication_manifest_changed')
    annotation = model.get('semantic_annotation', {})
    if not isinstance(annotation, dict):
        raise ValueError('annotation_invalid')
    return annotation.get('ontology_ref')


def reference_item(root, path, kind, ownership, ref):
    record = metadata(root, path)
    if not isinstance(record.get('space_id'), str):
        raise ValueError('ownership_unknown')
    if record['space_id'] != ownership['space_id']:
        return None
    match(record, ownership)
    identity = path.parent.name
    expected = r'build-[A-Za-z0-9-]+' if kind == 'candidate' else r'preview-[a-f0-9]{16}'
    if record.get('id') != identity or not re.fullmatch(expected, identity):
        raise ValueError('identity_mismatch')
    if kind == 'candidate' and record.get('state') != 'succeeded':
        return None
    if reference_model(root, path, kind, ownership, record) != ref:
        return None
    values = {'space': ownership['space_id']}
    if kind == 'candidate':
        route = 'data'; values.update(tab='versions', artifact='candidate:'+identity)
    else:
        route = 'delivery'; values['publication'] = identity
    return {'kind': kind, 'id': identity, 'href': '/'+route+'?'+urlencode(values),
            'ontology_ref': ref, 'integrity': 'metadata_only'}


def usage(jobs, directory, policy, principal, rules, query):
    policy.require(principal, query.space_id, 'data.manage')
    policy.require(principal, query.space_id, 'space.preview')
    ownership = scope(directory, query.space_id)
    rules.read(query.ontology_id, query.version, query.sha256)
    ref = {'ontology_id': query.ontology_id, 'version': query.version, 'sha256': query.sha256}
    items = []
    partial = False
    scanned = 0
    for kind, root, pattern in (('candidate', jobs.root, 'build-*/job.json'),
                                ('publication', jobs.root/'publications', 'preview-*/publication.json')):
        for path in root.glob(pattern):
            scanned += 1
            if scanned > MAX_RECORDS:
                partial = True
                break
            try:
                item = reference_item(root, path, kind, ownership, ref)
                if item is not None:
                    items.append(item)
            except (OSError, ValueError, KeyError, TypeError):
                partial = True
    items.sort(key=lambda item: (item['kind'], item['id']))
    return {'profile': 'cospace.scene-ontology-usage/0.1', 'space_id': query.space_id,
            'ontology_ref': ref, 'status': 'partial' if partial else 'ready',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'items': items[query.offset:query.offset+query.limit], 'total': len(items),
            'offset': query.offset, 'limit': query.limit,
            'next_offset': query.offset+query.limit if query.offset+query.limit < len(items) else None,
            'consistency': 'request_time_metadata_reads_not_transactional',
            'scope': 'single_scene_candidates_and_publications', 'source_files_rechecked': False}
