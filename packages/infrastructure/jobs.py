"""Transactional one-shot jobs; conditional updates serialize claims and cancellation."""
import uuid
from sqlalchemy import Column, ForeignKey, Integer, JSON, MetaData, String, Table, select, update
from packages.data.imports import canonical, sha, now
from packages.construction.errors import JobError


metadata = MetaData()
jobs = Table('cospace_jobs', metadata,
    Column('job_id', String, primary_key=True), Column('spec', JSON, nullable=False),
    Column('sha256', String, nullable=False), Column('state', String, nullable=False),
    Column('revision', Integer, nullable=False), Column('actor', String, nullable=False),
    Column('requested_at', String, nullable=False))
attempts = Table('cospace_attempts', metadata,
    Column('attempt_id', String, primary_key=True), Column('job_id', String, ForeignKey(jobs.c.job_id), nullable=False, unique=True),
    Column('state', String, nullable=False), Column('started_at', String, nullable=False),
    Column('finished_at', String), Column('diagnostic', JSON), Column('artifact', JSON))
events = Table('cospace_job_events', metadata,
    Column('event_id', String, primary_key=True), Column('job_id', String, ForeignKey(jobs.c.job_id), nullable=False),
    Column('state', String, nullable=False), Column('created_at', String, nullable=False))


def event(conn, identity, state):
    conn.execute(events.insert().values(event_id=uuid.uuid4().hex, job_id=identity, state=state, created_at=now()))


class JobStore:
    def __init__(self, engine):
        self.engine = engine

    def submit(self, spec, actor):
        identity = 'job-' + uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(jobs.insert().values(job_id=identity, spec=spec, sha256=sha(canonical(spec)),
                state='queued', revision=0, actor=actor, requested_at=now()))
            event(conn, identity, 'queued')
        return self.get(identity)

    def get(self, identity):
        with self.engine.begin() as conn:
            row = conn.execute(select(jobs).where(jobs.c.job_id == identity).with_for_update()).mappings().first()
            if row is None:
                raise JobError('job_not_found', 'job not found')
            result = dict(row)
            if sha(canonical(result['spec'])) != result['sha256']:
                raise JobError('content_corrupt', 'job specification digest mismatch')
            result['attempts'] = [dict(r) for r in conn.execute(select(attempts).where(attempts.c.job_id == identity)).mappings()]
            result['events'] = [dict(r) for r in conn.execute(select(events).where(events.c.job_id == identity)
                .order_by(events.c.created_at, events.c.event_id)).mappings()]
            return result

    def list(self, scene_id, limit=20, offset=0):
        with self.engine.connect() as conn:
            identities = conn.execute(select(jobs.c.job_id).where(jobs.c.spec['scene_id'].as_string() == scene_id)
                .order_by(jobs.c.requested_at.desc(), jobs.c.job_id.desc()).limit(limit + 1).offset(offset)).scalars().all()
        records = [self.get(identity) for identity in identities[:limit]]
        return {'scene_id': scene_id, 'items': [{key: row[key] for key in
            ('job_id', 'state', 'revision', 'requested_at', 'sha256', 'spec')} for row in records],
            'limit': limit, 'offset': offset, 'has_more': len(identities) > limit}

    def claim(self, identity, revision):
        attempt_id = 'attempt-' + uuid.uuid4().hex
        with self.engine.begin() as conn:
            result = conn.execute(update(jobs).where(jobs.c.job_id == identity, jobs.c.state == 'queued', jobs.c.revision == revision)
                .values(state='running', revision=revision + 1))
            if result.rowcount != 1:
                raise JobError('state_conflict', 'job cannot be claimed at requested revision')
            conn.execute(attempts.insert().values(attempt_id=attempt_id, job_id=identity, state='running', started_at=now()))
            event(conn, identity, 'running')
        return attempt_id

    def cancel(self, identity, revision):
        with self.engine.begin() as conn:
            result = conn.execute(update(jobs).where(jobs.c.job_id == identity, jobs.c.state == 'queued', jobs.c.revision == revision)
                .values(state='cancelled', revision=revision + 1))
            if result.rowcount != 1:
                raise JobError('state_conflict', 'only queued jobs can be cancelled at requested revision')
            event(conn, identity, 'cancelled')
        return self.get(identity)

    def finish(self, identity, attempt_id, diagnostic=None, artifact=None):
        state = 'failed' if diagnostic else 'succeeded'
        with self.engine.begin() as conn:
            result = conn.execute(update(attempts).where(attempts.c.attempt_id == attempt_id,
                attempts.c.job_id == identity, attempts.c.state == 'running').values(state=state,
                finished_at=now(), diagnostic=diagnostic, artifact=artifact))
            if result.rowcount != 1:
                raise JobError('state_conflict', 'attempt is no longer running')
            result = conn.execute(update(jobs).where(jobs.c.job_id == identity, jobs.c.state == 'running')
                .values(state=state, revision=jobs.c.revision + 1))
            if result.rowcount != 1:
                raise JobError('state_conflict', 'job is no longer running')
            event(conn, identity, state)
