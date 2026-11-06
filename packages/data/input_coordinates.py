"""Editable interpretation of one immutable input; jobs keep a fixed revision."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from pydantic import BaseModel, ConfigDict, Field, field_validator
from packages.data.preview_pointcloud import Coordinates, manifest, source_receipt
from packages.lifecycle.preview_control_lock import serialized


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


class CoordinatesConflict(ValueError): pass
class CoordinatesUnavailable(RuntimeError): pass


class CoordinateChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    expected_revision: int = Field(ge=0)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    coordinates: Coordinates
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('reason')
    @classmethod
    def text(cls, value):
        if not value.strip(): raise ValueError('reason_required')
        return value.strip()


def validate_coordinates(value):
    import re
    result = Coordinates.model_validate(value).model_dump()
    axes = result['axes']
    if len(set(axes)) != 3 or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}', a) for a in axes):
        raise ValueError('pointcloud_axes_invalid')
    return result


def interpret(checked, binding):
    """Validate original evidence before applying a frozen, explicit interpretation."""
    revision = binding.get('coordinate_revision')
    if not revision: return checked
    if (revision.get('profile') != 'cospace.input-coordinate-revision/0.1'
            or type(revision.get('revision')) is not int or revision['revision'] < 1
            or revision.get('input_id') != binding.get('id')
            or revision.get('space_id') != binding.get('space_id')
            or revision.get('source_snapshot_sha256') != checked['snapshot_sha256']
            or revision.get('source_cloud_sha256') != checked['cloud_sha256']):
        raise ValueError('coordinate_revision_binding_invalid')
    value = {k:v for k,v in revision.items() if k != 'sha256'}
    if checksum(value) != revision.get('sha256'): raise ValueError('coordinate_revision_integrity')
    return checked | validate_coordinates(revision['coordinates'])


class InputCoordinates:
    def __init__(self, catalog):
        self.catalog = catalog
        self.path = catalog.root / 'input-coordinates.sqlite3'

    def original(self, identity, space):
        record = self.catalog.read_original(identity)
        if record.get('space_id') != space or not space: raise PermissionError('input_not_in_space')
        return record

    def events(self, original):
        if not self.path.exists(): return []
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
                rows = db.execute('SELECT record FROM revisions WHERE input_id=? ORDER BY revision', (original['id'],)).fetchall()
            events = [json.loads(row[0]) for row in rows]
            for i, event in enumerate(events, 1):
                if (event['revision'] != i or not event['actor'] or not event['reason'].strip()
                        or event['before'] != (events[i-2]['coordinates'] if i > 1 else {k:original[k] for k in ('unit','frame_id','axes','scope','scene_alignment')})):
                    raise ValueError('coordinate_history_invalid')
                interpret(original, original | {'coordinate_revision':event})
            return events
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            raise CoordinatesUnavailable('input_coordinates_unavailable') from exc

    def effective(self, original):
        events = self.events(original)
        if not events: return original
        return original | events[-1]['coordinates'] | {'coordinate_revision':events[-1]}

    def fixed_records(self, original):
        """All audited bindings, for historical references; never used for new admission."""
        return [original, *[original | e['coordinates'] | {'coordinate_revision':e} for e in self.events(original)]]

    def read(self, identity, space):
        original = self.original(identity, space)
        supported = False
        if original['format'] == 'ply_pointcloud':
            doc, sha = manifest(original['snapshot'])
            if sha != original['snapshot_sha256']: raise ValueError('registered_input_changed')
            supported = bool(source_receipt(original['snapshot'], doc))
        events = self.events(original)
        coords = events[-1]['coordinates'] if events else ({k:original[k] for k in ('unit','frame_id','axes','scope','scene_alignment')} if original['format']=='ply_pointcloud' else None)
        return {'profile':'cospace.input-coordinates/0.1', 'input_id':identity, 'space_id':space,
                'supported':supported, 'revision':len(events), 'coordinates':coords, 'history':events}

    @serialized(lambda self:self.catalog.root.parent)
    def change(self, identity, change, actor):
        original = self.original(identity, change.space_id)
        state = self.read(identity, change.space_id)
        if not state['supported']: raise ValueError('coordinate_edit_unsupported')
        request_sha = checksum(change.model_dump())
        prior = next((e for e in state['history'] if e['request_id']==change.request_id), None)
        if prior:
            if prior['request_sha256'] != request_sha: raise CoordinatesConflict('coordinate_request_conflict')
            return state
        if state['revision'] != change.expected_revision: raise CoordinatesConflict('coordinate_revision_changed')
        from packages.lifecycle.preview_control import PreviewControls
        PreviewControls(self.catalog.root.parent, self.catalog.directory).require_active(change.space_id, 'input:'+identity)
        self.catalog.resolve(identity)
        coords = validate_coordinates(change.coordinates.model_dump())
        if coords == state['coordinates']: return state
        event = {'profile':'cospace.input-coordinate-revision/0.1', 'input_id':identity, 'space_id':change.space_id,
                 'revision':state['revision']+1, 'before':state['coordinates'], 'coordinates':coords,
                 'source_snapshot_sha256':original['snapshot_sha256'], 'source_cloud_sha256':original['cloud_sha256'],
                 'actor':actor, 'changed_at':datetime.now(timezone.utc).isoformat(), 'reason':change.reason,
                 'request_id':change.request_id, 'request_sha256':request_sha}
        event['sha256'] = checksum(event)
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as db:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS revisions(input_id TEXT NOT NULL, revision INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(input_id,revision))')
                    db.execute('INSERT INTO revisions VALUES(?,?,?)', (identity,event['revision'],json.dumps(event,ensure_ascii=False)))
        except (OSError, sqlite3.Error) as exc: raise CoordinatesUnavailable('input_coordinates_unavailable') from exc
        return self.read(identity, change.space_id)
