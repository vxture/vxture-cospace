"""Experimental F01/F02 metadata validation; does not authorize algorithm input."""
import json
import math
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/schemas/observation-input-v0.1.schema.json'


def validate_observation_input(document):
    """Raise ValueError on bad metadata. No payload files or evidence are verified."""
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('non_finite_number')
        if isinstance(value, dict):
            for item in value.values():
                finite(item)
        elif isinstance(value, list):
            for item in value:
                finite(item)

    finite(document)
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document))
    if errors:
        error = errors[0]
        raise ValueError(f'structure:{"/".join(map(str, error.absolute_path))}: {error.message}')

    def utc(value):
        # jsonschema's date-time checker can be unavailable without optional extras.
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', value):
            raise ValueError('structure:invalid_utc_timestamp')
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as error:
            raise ValueError('structure:invalid_utc_calendar_date') from error

    def identities(items, key):
        values = [item[key] for item in items]
        if len(set(values)) != len(values):
            raise ValueError(f'duplicate:{key}')
        return set(values)

    frames = identities(document['frames'], 'frame_id')
    members = identities(document['members'], 'member_id')
    identities(document['streams'], 'stream_id')
    identities(document['reference_points'], 'point_id')
    paths = set()
    for member in document['members']:
        path = member['path']
        # Portable package-relative paths only; never use this as filesystem verification.
        if ('\\' in path or re.search(r'[:\x00-\x1f]', path) or
                any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in path.split('/'))):
            raise ValueError('unsafe_member_path')
        if path.casefold() in paths:
            raise ValueError('duplicate_member_path')
        paths.add(path.casefold())
        if type(member['bytes']) is not int:
            raise ValueError('bytes_must_be_literal_integer')

    def frame_ref(value):
        if value not in frames:
            raise ValueError(f'unknown_frame:{value}')

    for stream in document['streams']:
        frame_ref(stream['frame_id'])
        if stream['member_id'] not in members:
            raise ValueError('unknown_member')
        identities(stream['fields'], 'name')
        clock = stream['clock']
        if 'utc_start' in clock:
            start = utc(clock['utc_start'])
            end = utc(clock['utc_end'])
            if end < start:
                raise ValueError('reversed_observation_interval')
        if clock['sync_status'] == 'verified' and clock['time_scale'] == 'unknown':
            raise ValueError('verified_clock_requires_known_scale')
    for point in document['reference_points']:
        frame_ref(point['frame_id'])
        utc(point['measured_at'])

    parents = {}
    for transform in document['transforms']:
        source, target = transform['source_frame_id'], transform['target_frame_id']
        frame_ref(source)
        frame_ref(target)
        if source == target or source in parents:
            raise ValueError('ambiguous_transform_parent')
        parents[source] = target
        m = transform['matrix']
        if any(abs(m[3][i] - expected) > 1e-9 for i, expected in enumerate((0, 0, 0, 1))):
            raise ValueError('invalid_homogeneous_row')
        for i in range(3):
            for j in range(3):
                dot = sum(m[k][i] * m[k][j] for k in range(3))
                if abs(dot - (1 if i == j else 0)) > 1e-6:
                    raise ValueError('non_rigid_rotation')
        a, b, c = m[0][:3], m[1][:3], m[2][:3]
        determinant = (a[0] * (b[1]*c[2]-b[2]*c[1]) -
                       a[1] * (b[0]*c[2]-b[2]*c[0]) + a[2] * (b[0]*c[1]-b[1]*c[0]))
        if abs(determinant - 1) > 1e-6:
            raise ValueError('reflection_not_allowed')
    for source in parents:
        visited = set()
        while source in parents:
            if source in visited:
                raise ValueError('transform_cycle')
            visited.add(source)
            source = parents[source]
    return {'schema_version': document['schema_version'], 'metadata_valid': True,
            'payload_verified': False, 'evidence_verified': False,
            'algorithm_ready': False, 'real_release_ready': False}
