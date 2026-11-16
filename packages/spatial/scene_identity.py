"""SG1 synthetic identity proposals bound to two immutable graph documents."""
import hashlib
import json
from collections import defaultdict
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from packages.spatial.scene_graph import Fixed, Identity, validate_scene_graph

Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


def canonical(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def content_digest(document):
    return hashlib.sha256(canonical(document)).hexdigest()


class SnapshotRef(Fixed):
    scene_id: Identity
    snapshot_id: Identity
    sha256: Digest


def snapshot_ref(document):
    validate_scene_graph(document)
    return {key: document[key] for key in ('scene_id', 'snapshot_id')} | {'sha256': content_digest(document)}


class IdentityEvent(Fixed):
    id: Identity
    kind: Literal['split', 'merge', 'unresolved']
    before_ids: Annotated[list[Identity], Field(min_length=1, max_length=32)]
    after_ids: Annotated[list[Identity], Field(min_length=1, max_length=32)]
    assessment: Literal['unverified']
    reason: Annotated[str, Field(min_length=1, max_length=512)]


class IdentityChanges(Fixed):
    profile: Literal['cospace.synthetic-identity-changes/0.1']
    data_kind: Literal['synthetic']
    base: SnapshotRef
    target: SnapshotRef
    events: Annotated[list[IdentityEvent], Field(max_length=1000)]


def _unique_refs(event):
    if len(set(event.before_ids)) != len(event.before_ids) or len(set(event.after_ids)) != len(event.after_ids):
        raise ValueError('duplicate_identity_reference')
    if set(event.before_ids) & set(event.after_ids):
        raise ValueError('identity_event_reuses_id')


def _event_shape(event, before, after):
    _unique_refs(event)
    if set(event.before_ids) - before.keys() or set(event.after_ids) - after.keys():
        raise ValueError('identity_endpoint_missing')
    cardinalities = (len(event.before_ids), len(event.after_ids))
    if event.kind == 'split' and not (cardinalities[0] == 1 and cardinalities[1] >= 2):
        raise ValueError('split_cardinality')
    if event.kind == 'merge' and not (cardinalities[0] >= 2 and cardinalities[1] == 1):
        raise ValueError('merge_cardinality')
    endpoints = [before[i] for i in event.before_ids] + [after[i] for i in event.after_ids]
    if len({e['kind'] for e in endpoints}) != 1:
        raise ValueError('identity_kind_mismatch')


def _event_membership(event, before, after, used_before, used_after):
    if set(event.before_ids) & used_before or set(event.after_ids) & used_after:
        raise ValueError('overlapping_identity_events')
    # Split/merge and unresolved correspondence must retire old IDs and use fresh IDs.
    # In-place edits retain their identity and are represented as revisions, not these events.
    if set(event.before_ids) & after.keys() or set(event.after_ids) & before.keys():
        raise ValueError('identity_endpoint_still_continues')
    used_before.update(event.before_ids)
    used_after.update(event.after_ids)


def _continued_revisions(base, target):
    before = {e['id']: e for e in base['entities']}
    after = {e['id']: e for e in target['entities']}
    if base['ontology'] != target['ontology'] or base['frame'] != target['frame']:
        raise ValueError('identity_context_migration_unsupported')
    base_geometry, target_geometry = _geometry_by_entity(base), _geometry_by_entity(target)
    for identity in before.keys() & after.keys():
        a, b = before[identity], after[identity]
        if a['kind'] != b['kind']:
            raise ValueError('continued_identity_kind_changed')
        if b['revision'] < a['revision']:
            raise ValueError('identity_revision_regression')
        if (a | {'revision': 0}) != (b | {'revision': 0}) or base_geometry[identity] != target_geometry[identity]:
            if b['revision'] <= a['revision']:
                raise ValueError('changed_entity_requires_revision')
    return before, after


def _geometry_by_entity(document):
    result = defaultdict(dict)
    for item in document['geometry']:
        result[item['entity_id']][item['id']] = item
    return result


def validate_identity_changes(document, base, target):
    try:
        changes = IdentityChanges.model_validate(document)
    except ValidationError as exc:
        raise ValueError('identity_structure:' + str(exc)) from exc
    if changes.base.model_dump() != snapshot_ref(base) or changes.target.model_dump() != snapshot_ref(target):
        raise ValueError('identity_snapshot_binding')
    if base['scene_id'] != target['scene_id'] or base['snapshot_id'] == target['snapshot_id']:
        raise ValueError('identity_snapshot_scope')
    before, after = _continued_revisions(base, target)
    used_before, used_after, event_ids = set(), set(), set()
    for event in changes.events:
        if event.id in event_ids:
            raise ValueError('duplicate_identity_event')
        event_ids.add(event.id)
        _event_shape(event, before, after)
        _event_membership(event, before, after, used_before, used_after)
    return {'metadata_valid': True, 'data_kind': 'synthetic',
            'continued_ids': sorted(before.keys() & after.keys()),
            'added_ids': sorted(after.keys() - before.keys() - used_after),
            'removed_ids': sorted(before.keys() - after.keys() - used_before),
            'unresolved_event_ids': [e.id for e in changes.events if e.kind == 'unresolved'],
            'identity_verified': False, 'mutation_supported': False,
            'real_release_ready': False, 'robot_ready': False}
