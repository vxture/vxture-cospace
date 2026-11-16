"""Bounded single-host observation persistence; callers own authorization."""
from contextlib import closing
from pathlib import Path
import sqlite3

from packages.spatial.scene_graph import utc
from packages.spatial.scene_identity import canonical, content_digest
from packages.spatial.opening_observations import (
    Registration, Report, now_utc, scope_key, validate_correction, resolve_reports,
)

MAX_EVENTS = 5000
MAX_BATCH = 128


def _initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS registrations (scope TEXT PRIMARY KEY, document BLOB NOT NULL)')
    db.execute('''CREATE TABLE IF NOT EXISTS reports (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, producer TEXT NOT NULL,
        event_id TEXT NOT NULL, received_at TEXT NOT NULL, document BLOB NOT NULL, supersedes TEXT,
        UNIQUE(scope, producer, event_id), UNIQUE(scope, producer, supersedes))''')
    db.execute('CREATE INDEX IF NOT EXISTS reports_scope_seq ON reports(scope,seq)')


def _registration(db, key):
    row = db.execute('SELECT document FROM registrations WHERE scope=?', (key,)).fetchone()
    if row is None:
        raise ValueError('observation_scope_not_registered')
    return Registration.model_validate_json(row[0])


def _records(db, key):
    rows = db.execute('SELECT seq, received_at, document FROM reports WHERE scope=? ORDER BY seq LIMIT ?',
                      (key, MAX_EVENTS + 1)).fetchall()
    if len(rows) > MAX_EVENTS:
        raise ValueError('observation_read_budget')
    return [{'sequence': seq, 'received_at': received,
             'report': Report.model_validate_json(raw).model_dump()} for seq, received, raw in rows]


def _event(db, key, producer, event_id):
    row = db.execute('SELECT seq, received_at, document FROM reports WHERE scope=? AND producer=? AND event_id=?',
                     (key, producer, event_id)).fetchone()
    if row is None:
        return None
    return {'sequence': row[0], 'received_at': row[1], 'report': Report.model_validate_json(row[2]).model_dump()}


def _check_correction(db, key, report):
    if report.supersedes is None:
        return
    previous = _event(db, key, report.producer, report.supersedes)
    corrected = db.execute('SELECT 1 FROM reports WHERE scope=? AND producer=? AND supersedes=?',
                           (key, report.producer, report.supersedes)).fetchone() is not None
    validate_correction(report, previous['report'] if previous else None, already_corrected=corrected)


class ObservationJournal:
    """Single-host append-only journal. No HTTP, authorization or model promotion."""

    def __init__(self, root, *, clock=now_utc):
        self.path = Path(root).resolve() / 'spatial-observations.sqlite3'
        self.clock = clock

    def register(self, document):
        registration = Registration.model_validate(document)
        raw, key = canonical(registration.model_dump()), scope_key(registration.scope)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            _initialize(db)
            current = db.execute('SELECT document FROM registrations WHERE scope=?', (key,)).fetchone()
            if current is not None and current[0] != raw:
                raise ValueError('observation_registration_immutable')
            db.execute('INSERT OR IGNORE INTO registrations VALUES (?,?)', (key, raw))
        return key

    def registered(self, scope):
        key = scope_key(scope)
        if not self.path.exists():
            return False
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            return db.execute('SELECT 1 FROM registrations WHERE scope=?', (key,)).fetchone() is not None

    def append(self, scope, document, *, authenticated_producer):
        return self.append_batch(scope, [document], authenticated_producer=authenticated_producer)[0]

    def append_batch(self, scope, documents, *, authenticated_producer):
        if not isinstance(documents, list) or not 1 <= len(documents) <= MAX_BATCH:
            raise ValueError('observation_batch_budget')
        reports, key = [Report.model_validate(row) for row in documents], scope_key(scope)
        if any(report.producer != authenticated_producer for report in reports):
            raise ValueError('observation_producer_mismatch')
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            registration = _registration(db, key)
            subjects = {s.entity_id for s in registration.subjects}
            if authenticated_producer not in registration.producers or any(report.entity_id not in subjects for report in reports):
                raise ValueError('observation_reference_not_registered')
            return [self._append(db, key, report) for report in reports]

    def _append(self, db, key, report):
        raw = canonical(report.model_dump())
        previous = _event(db, key, report.producer, report.event_id)
        if previous is not None:
            if canonical(previous['report']) != raw:
                raise ValueError('observation_event_immutable')
            return previous
        if db.execute('SELECT COUNT(*) FROM reports WHERE scope=?', (key,)).fetchone()[0] >= MAX_EVENTS:
            raise ValueError('observation_write_budget')
        _check_correction(db, key, report)
        received = self.clock()
        previous_time = db.execute('SELECT received_at FROM reports WHERE scope=? ORDER BY seq DESC LIMIT 1', (key,)).fetchone()
        if previous_time and utc(received) < utc(previous_time[0]):
            raise ValueError('observation_server_clock_reversed')
        utc(received)
        if utc(report.observed_at) > utc(received):
            raise ValueError('observation_future_report')
        cursor = db.execute('INSERT INTO reports(scope,producer,event_id,received_at,document,supersedes) VALUES (?,?,?,?,?,?)',
                            (key, report.producer, report.event_id, received, raw, report.supersedes))
        return {'sequence': cursor.lastrowid, 'received_at': received, 'report': report.model_dump()}

    def resolve(self, scope, entity, *, as_of, known_at, through_sequence=None):
        key, when, known = scope_key(scope), utc(as_of), utc(known_at)
        if through_sequence is not None and (type(through_sequence) is not int or through_sequence < 0):
            raise ValueError('observation_invalid_sequence')
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db, db:
            registration = _registration(db, key)
            if entity not in {s.entity_id for s in registration.subjects}:
                raise ValueError('observation_subject_not_registered')
            records = _records(db, key)
        ceiling = max((r['sequence'] for r in records), default=0)
        if through_sequence is not None:
            if through_sequence > ceiling:
                raise ValueError('observation_sequence_unavailable')
            ceiling = through_sequence
        records = [r for r in records if r['sequence'] <= ceiling and utc(r['received_at']) <= known]
        status, value, latest, active, retracted = resolve_reports(records, entity, when)
        received_times = [r['received_at'] for r in records if r['report']['entity_id'] == entity
                          and utc(r['report']['observed_at']) <= when]
        context = {'scope': registration.scope.model_dump(), 'registration_sha256': content_digest(registration.model_dump()),
                   'entity_id': entity, 'as_of': as_of, 'known_at': known_at, 'through_sequence': ceiling,
                   'policy': 'cospace.reported-opening-state/0.1', 'records_sha256': content_digest(records)}
        return {'profile': 'cospace.reported-opening-state/0.1', **context, 'status': status, 'value': value,
                'active': active, 'retracted': retracted,
                'last_received_at': max(received_times, key=utc, default=None),
                'expired': [r for r in latest if utc(r['report']['valid_until']) <= when], 'cursor': content_digest(context),
                'data_kind': registration.data_kind, 'assessment': 'unverified', 'evidence_content_verified': False,
                'source_content_verified': False, 'clock_quality_verified': False, 'real_release_ready': False,
                'limitations': ['producer_reports_not_field_truth', 'no_source_priority', 'no_navigation_or_traversability',
                                'no_automatic_rebuild', 'single_host_bounded_journal']}
