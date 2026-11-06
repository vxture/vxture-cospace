"""Explicit versioned sample database setup; URL only comes from environment."""
import os

from alembic import context
from sqlalchemy import create_engine

from packages.infrastructure.releases import metadata
from packages.infrastructure.imports import metadata as import_metadata
from packages.infrastructure.jobs import metadata as job_metadata


def migrate(connection):
    context.configure(connection=connection, target_metadata=[metadata, import_metadata, job_metadata], compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get('connection')
if connection is not None:
    migrate(connection)
else:
    url = os.environ.get('COSPACE_DATABASE_URL')
    if not url:
        raise RuntimeError('COSPACE_DATABASE_URL required for migrations')
    engine = create_engine(url)
    try:
        if engine.dialect.name != 'postgresql':
            raise RuntimeError('migration CLI requires PostgreSQL')
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
