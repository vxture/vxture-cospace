"""Transactional import identity and immutable dataset references."""
from sqlalchemy import Column, ForeignKey, JSON, MetaData, String, Table, UniqueConstraint, select, update
from sqlalchemy.exc import IntegrityError
from packages.data.imports import ImportError, canonical, sha

metadata = MetaData()
imports = Table('cospace_imports', metadata,
    Column('import_id', String, primary_key=True), Column('scene_id', String, nullable=False),
    Column('idempotency_key', String, nullable=False), Column('request_sha256', String, nullable=False),
    Column('request', JSON, nullable=False), Column('actor', String, nullable=False),
    Column('requested_at', String, nullable=False), Column('state', String, nullable=False),
    Column('diagnostic', JSON), Column('dataset_id', String), Column('committed_at', String),
    UniqueConstraint('scene_id', 'idempotency_key', name='uq_cospace_import_request'))
datasets = Table('cospace_datasets', metadata,
    Column('dataset_id', String, primary_key=True),
    Column('import_id', String, ForeignKey(imports.c.import_id), nullable=False, unique=True),
    Column('manifest', JSON, nullable=False), Column('sha256', String, nullable=False))


class ImportStore:
    def __init__(self, engine):
        self.engine = engine

    def claim(self, identity, request, digest, actor, timestamp):
        try:
            with self.engine.begin() as conn:
                conn.execute(imports.insert().values(import_id=identity, scene_id=request['scene_id'],
                    idempotency_key=request['idempotency_key'], request_sha256=digest, request=request,
                    actor=actor, requested_at=timestamp, state='receiving'))
            return self.get_import(identity), True
        except IntegrityError:
            with self.engine.connect() as conn:
                row = conn.execute(select(imports).where(imports.c.scene_id == request['scene_id'],
                    imports.c.idempotency_key == request['idempotency_key'])).mappings().first()
                if row is None:
                    raise
                if row['request_sha256'] != digest:
                    raise ImportError('idempotency_conflict', 'key already binds a different request')
                return dict(row), False

    def get_import(self, identity):
        with self.engine.connect() as conn:
            row = conn.execute(select(imports).where(imports.c.import_id == identity)).mappings().first()
            if row is None:
                raise ImportError('import_not_found', 'import not found')
            return dict(row)

    def state(self, identity, state):
        with self.engine.begin() as conn:
            result = conn.execute(update(imports).where(imports.c.import_id == identity, imports.c.state == 'receiving').values(state=state))
            if result.rowcount != 1:
                raise ImportError('state_conflict', 'import is no longer receiving')

    def reject(self, identity, diagnostic):
        with self.engine.begin() as conn:
            conn.execute(update(imports).where(imports.c.import_id == identity,
                imports.c.state.in_(['receiving', 'validating'])).values(state='rejected', diagnostic=diagnostic))

    def commit(self, identity, manifest, digest, timestamp):
        with self.engine.begin() as conn:
            result = conn.execute(update(imports).where(imports.c.import_id == identity, imports.c.state == 'validating')
                .values(state='committed', dataset_id=manifest['dataset_id'], committed_at=timestamp))
            if result.rowcount != 1:
                raise ImportError('state_conflict', 'import is no longer validating')
            conn.execute(datasets.insert().values(dataset_id=manifest['dataset_id'], import_id=identity,
                                                   manifest=manifest, sha256=digest))

    def get_dataset(self, identity):
        with self.engine.connect() as conn:
            row = conn.execute(select(datasets).where(datasets.c.dataset_id == identity)).mappings().first()
            if row is None:
                raise ImportError('dataset_not_found', 'dataset not found')
            record = dict(row)
            if sha(canonical(record['manifest'])) != record['sha256']:
                raise ImportError('content_corrupt', 'dataset manifest digest mismatch')
            return record
