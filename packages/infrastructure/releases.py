"""SQLAlchemy sample storage. PostgreSQL is the supported concurrency path."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import uuid

from sqlalchemy import (Column, ForeignKey, Integer, JSON, MetaData, String, Table,
                        select, update)
from sqlalchemy.exc import IntegrityError

from packages.lifecycle.releases import ReleaseError


metadata = MetaData()
scenes = Table('cospace_sample_scenes', metadata,
    Column('scene_id', String, primary_key=True),
    Column('release_id', String, nullable=True), Column('revision', Integer, nullable=False))
releases = Table('cospace_sample_releases', metadata,
    Column('scene_id', String, ForeignKey(scenes.c.scene_id), primary_key=True),
    Column('release_id', String, primary_key=True),
    Column('payload', JSON, nullable=False), Column('sha256', String, nullable=False))
events = Table('cospace_sample_events', metadata,
    Column('event_id', String, primary_key=True), Column('scene_id', String, nullable=False),
    Column('release_id', String, nullable=False), Column('kind', String, nullable=False),
    Column('actor', String, nullable=False), Column('reason', String, nullable=False),
    Column('created_at', String, nullable=False), Column('revision', Integer, nullable=True))
references = Table('cospace_sample_references', metadata,
    Column('scene_id', String, primary_key=True), Column('kind', String, primary_key=True),
    Column('identity', String, primary_key=True), Column('sha256', String, nullable=False))


def digest(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class ReleaseStore:
    def __init__(self, engine):
        self.engine = engine

    def initialize_demo(self):
        from packages.infrastructure.migrations import migrate_database
        migrate_database(self.engine)

    def register(self, scene_id, release_id, payload):
        checksum = digest(payload)
        # Establish the lock row, tolerating a competing first registration.
        try:
            with self.engine.begin() as conn:
                if conn.execute(select(scenes.c.scene_id).where(scenes.c.scene_id == scene_id)).first() is None:
                    conn.execute(scenes.insert().values(scene_id=scene_id, release_id=None, revision=0))
        except IntegrityError:
            pass
        with self.transaction(scene_id) as tx:
            existing = tx.conn.execute(select(releases).where(
                releases.c.scene_id == scene_id, releases.c.release_id == release_id)).mappings().first()
            if existing:
                if existing['sha256'] != checksum:
                    raise ReleaseError('immutable_conflict', 'release identity already binds different content')
                tx.load(release_id)
                return
            snapshot = payload['snapshot']
            truth = snapshot['release']['source_truth']
            ontology = snapshot['truth']['ontology_ref']
            fixed = [('truth', truth['truth_version_id'], truth['sha256']),
                     ('ontology', json.dumps([ontology['ontology_id'], ontology['version']]), ontology['sha256'])]
            fixed += [('view', ref['view_version_id'], ref['sha256']) for ref in snapshot['release']['views']]
            for kind, identity, sha256 in fixed:
                predicate = (references.c.scene_id == scene_id, references.c.kind == kind,
                             references.c.identity == identity)
                prior = tx.conn.execute(select(references.c.sha256).where(*predicate)).scalar_one_or_none()
                if prior is not None and prior != sha256:
                    raise ReleaseError('immutable_conflict', f'{kind} identity already binds different content')
                if prior is None:
                    tx.conn.execute(references.insert().values(scene_id=scene_id, kind=kind,
                                                              identity=identity, sha256=sha256))
            tx.conn.execute(releases.insert().values(scene_id=scene_id, release_id=release_id,
                                                     payload=payload, sha256=checksum))

    @contextmanager
    def transaction(self, scene_id):
        with self.engine.begin() as conn:
            row = conn.execute(select(scenes).where(scenes.c.scene_id == scene_id)
                               .with_for_update()).mappings().first()
            if row is None:
                raise ReleaseError('scene_not_found', 'sample scene not registered')
            yield Transaction(conn, dict(row))


class Transaction:
    def __init__(self, conn, scene):
        self.conn, self.scene = conn, scene

    def current(self):
        return {key: self.scene[key] for key in ('release_id', 'revision')}

    def load(self, release_id):
        row = self.conn.execute(select(releases).where(
            releases.c.scene_id == self.scene['scene_id'], releases.c.release_id == release_id)).mappings().first()
        if row is None:
            raise ReleaseError('release_not_found', 'sample release not registered')
        if digest(row['payload']) != row['sha256']:
            raise ReleaseError('content_corrupt', 'stored release snapshot integrity mismatch')
        return row['payload']

    def revocations(self, release_id):
        rows = self.conn.execute(select(events).where(
            events.c.scene_id == self.scene['scene_id'], events.c.release_id == release_id,
            events.c.kind == 'revoke').order_by(events.c.created_at, events.c.event_id)).mappings()
        return [dict(row) for row in rows]

    def event(self, release_id, kind, actor, reason='', revision=None):
        record = dict(event_id=uuid.uuid4().hex, scene_id=self.scene['scene_id'],
                      release_id=release_id, kind=kind, actor=actor, reason=reason,
                      revision=revision, created_at=datetime.now(timezone.utc).isoformat())
        self.conn.execute(events.insert().values(**record))
        return record

    def activate(self, release_id, actor):
        revision = self.scene['revision'] + 1
        result = self.conn.execute(update(scenes).where(
            scenes.c.scene_id == self.scene['scene_id'], scenes.c.revision == self.scene['revision'])
            .values(release_id=release_id, revision=revision))
        if result.rowcount != 1:
            raise ReleaseError('revision_conflict', 'concurrent pointer update')
        self.event(release_id, 'activate', actor, revision=revision)
        return {'release_id': release_id, 'revision': revision}

    def revoke(self, release_id, actor, reason):
        return self.event(release_id, 'revoke', actor, reason)
