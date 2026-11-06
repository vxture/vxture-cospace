"""Application-independent Alembic entry with optional existing transaction."""
from pathlib import Path

from alembic import command
from alembic.config import Config


def migrate_database(engine, direction='upgrade'):
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        if direction == 'upgrade':
            command.upgrade(config, 'head')
        elif direction == 'downgrade':
            command.downgrade(config, 'base')
        else:
            raise ValueError('unsupported migration direction')
