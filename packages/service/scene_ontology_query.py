"""Read-only object join over one explicit consumer revision and fixed model.

All geographic handoff stays unavailable until a verified transform adapter is
connected. Model anchors and semantic claims retain distinct evidence scopes.
"""
from copy import deepcopy
from datetime import datetime
import math
import re

from packages.service.scene_ontology_links import require
from packages.service.scene_ontology_validation import validate_link_properties, validate_link_relations


def timestamp(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value) is not None,
            'invalid_query_time')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        require(False, 'invalid_query_time')


def time_state(period, instant):
    if period is None:
        return 'not_recorded'
    try:
        start = timestamp(period['start'])
        end = timestamp(period['end']) if period['end'] is not None else None
    except (ValueError, KeyError, TypeError):
        return 'invalid'
    if end is not None and end <= start:
        return 'invalid'
    if instant is None:
        return 'not_filtered'
    return 'active' if start <= instant and (end is None or instant < end) else 'inactive'


def finite_coordinate(value):
    if type(value) is int:
        return value.bit_length() <= 1023
    return type(value) is float and math.isfinite(value)


def model_location(source, obj):
    point = obj.get('anchor_m')
    evidence = obj.get('evidence', {})
    available = (source.get('unit') == 'm' and type(source.get('frame_id')) is str and bool(source['frame_id'])
        and type(point) is list and len(point) == 3 and all(finite_coordinate(value) for value in point)
        and evidence.get('kind') == 'model_point' and evidence.get('member') == 'spatial.npz'
        and type(evidence.get('point_index')) is int and evidence['point_index'] >= 0
        and type(source.get('source_model_sha256')) is str
        and re.fullmatch('[a-f0-9]{64}', source['source_model_sha256']) is not None
        and evidence.get('sha256') == source['source_model_sha256'])
    axes = source.get('axes')
    preview_available = available and type(axes) is list and len(axes) == 3 and all(type(axis) is str and bool(axis) for axis in axes)
    result = {'preview_available': bool(preview_available), 'available': bool(available), 'kind': 'fixed_model_point', 'field_verified': False,
              'geographic_location': {'available': False, 'reason': 'geographic_handoff_not_connected'}}
    if not preview_available:
        result['preview_reason'] = 'model_axes_not_recorded' if available else 'verified_model_anchor_not_available'
    if available:
        result.update(position=deepcopy(point), frame_id=source['frame_id'], unit='m', evidence=deepcopy(evidence))
    else:
        result['reason'] = 'verified_model_anchor_not_available'
    return result


def query_object(source, snapshot, identity, at=None):
    require(type(identity) is str and 1 <= len(identity) <= 160)
    instant = timestamp(at) if at is not None else None
    obj = next((item for item in source['objects'] if item['object_id'] == identity), None)
    require(obj is not None, 'object_not_found')
    link = next((item for item in snapshot['links'] if item['object_id'] == identity), None)
    attributes = validate_link_properties(source, snapshot)
    relations = validate_link_relations(source, snapshot)
    mappings = []
    for item in snapshot.get('relation_links', []):
        if identity not in (item['source_id'], item['target_id']):
            continue
        mapping = {key: deepcopy(value) for key, value in item.items() if key != 'bundle'}
        mapping['time_state'] = time_state(item['valid_time'], instant)
        mappings.append(mapping)
    claim = None
    if link:
        claim = {key: deepcopy(value) for key, value in link.items() if key != 'bundle'}
        claim['time_state'] = time_state(link.get('instance_valid_time'), instant)
    return {'profile': 'cospace.scene-ontology-object-view/0.1', 'space_id': source['space_id'],
            'candidate_id': source['candidate_id'], 'source_sha256': source['source_sha256'],
            'revision': snapshot['revision'], 'object_id': identity, 'name': obj['properties'].get('name', identity),
            'at': at, 'time_query_policy': 'classify_without_inference', 'claim': claim,
            'model_location': model_location(source, obj), 'relations': mappings,
            'attribute_report': attributes, 'relation_report': relations,
            'included_in_publication': False, 'professional_review': 'not_performed'}
