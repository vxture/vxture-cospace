"""Cold journal validation for operator backups, not producer or evidence certification."""
from contextlib import closing
from pathlib import Path
import sqlite3

from packages.infrastructure.spatial_observation_store import (
    MAX_EVENTS, _initialize, _decode_registration, _decode_record,
)
from packages.spatial.opening_observations import Report, validate_correction
from packages.spatial.scene_graph import utc
from packages.spatial.scene_identity import canonical

MAX_SCOPES = 1000
MAX_TOTAL_EVENTS = 100_000


def _schema(db):
    return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def _validate_sequence(db):
    maximum = db.execute('SELECT COALESCE(MAX(seq),0) FROM reports').fetchone()[0]
    sequence = db.execute('SELECT name,seq FROM sqlite_sequence').fetchall()
    if (sequence and (len(sequence) != 1 or sequence[0][0] != 'reports'
                      or type(sequence[0][1]) is not int or sequence[0][1] < maximum)
            or maximum > 0 and not sequence):
        raise ValueError('observation_integrity_sequence')
    return maximum


def _records(db, key, registration):
    rows = db.execute('SELECT seq,producer,event_id,received_at,document,supersedes FROM reports '
                      'WHERE scope=? ORDER BY seq LIMIT ?', (key, MAX_EVENTS + 1)).fetchall()
    if len(rows) > MAX_EVENTS:
        raise ValueError('observation_integrity_scope_budget')
    subjects = {s.entity_id for s in registration.subjects}
    previous, corrected, last_received = {}, set(), None
    for sequence, producer, event, received, raw, supersedes in rows:
        record = _decode_record(sequence, received, raw)
        report = record['report']
        if (type(sequence) is not int or sequence <= 0 or canonical(report) != raw
                or (producer, event, supersedes) != (report['producer'], report['event_id'], report['supersedes'])
                or producer not in registration.producers or report['entity_id'] not in subjects
                or utc(report['observed_at']) > utc(received)
                or last_received is not None and utc(received) < last_received):
            raise ValueError('observation_integrity_record_binding')
        model = Report.model_validate(report)
        target = (producer, supersedes)
        validate_correction(model, previous.get(target), already_corrected=target in corrected)
        if supersedes is not None:
            corrected.add(target)
        previous[(producer, event)] = report
        last_received = utc(received)
    return len(rows)


def validate_observation_database(path):
    """Caller must stop writers/hold the runtime mutation lock; opens no new database."""
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.is_junction():
        raise ValueError('observation_integrity_regular_file_required')
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('observation_integrity_cold_database_required')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('observation_integrity_database')
        with closing(sqlite3.connect(':memory:')) as expected:
            _initialize(expected)
            if _schema(db) != _schema(expected) or db.execute('PRAGMA user_version').fetchone()[0] != 0:
                raise ValueError('observation_integrity_schema')
        scopes = db.execute('SELECT scope,document FROM registrations ORDER BY scope LIMIT ?', (MAX_SCOPES + 1,)).fetchall()
        total = db.execute('SELECT COUNT(*) FROM reports').fetchone()[0]
        if len(scopes) > MAX_SCOPES or total > MAX_TOTAL_EVENTS:
            raise ValueError('observation_integrity_total_budget')
        if db.execute('SELECT 1 FROM reports r LEFT JOIN registrations s ON r.scope=s.scope '
                      'WHERE s.scope IS NULL LIMIT 1').fetchone():
            raise ValueError('observation_integrity_orphan_scope')
        for key, raw in scopes:
            registration = _decode_registration(raw, key)
            if canonical(registration.model_dump()) != raw:
                raise ValueError('observation_integrity_registration_encoding')
            _records(db, key, registration)
        return {'registrations': len(scopes), 'reports': total, 'highest_sequence': _validate_sequence(db)}
