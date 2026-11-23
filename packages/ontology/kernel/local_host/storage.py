"""Standalone state, with a single snapshot for definitions and group configuration."""
from contextlib import closing
from pathlib import Path
import sqlite3

FILENAME = 'ontology-host.sqlite3'
APPLICATION_ID = 0x56584F48  # VXOH
SCHEMA_VERSION = 1


def connect(path, *, readonly=False):
    # URI mode prevents backup/restore reads from ever creating a source file.
    connection = sqlite3.connect(path.resolve().as_uri() + ('?mode=ro' if readonly else '?mode=rwc'), uri=True,
                                 timeout=10)
    connection.execute('PRAGMA trusted_schema=OFF')
    return connection


def identity(connection):
    app_id = connection.execute('PRAGMA application_id').fetchone()[0]
    version = connection.execute('PRAGMA user_version').fetchone()[0]
    return app_id, version


def check(connection):
    if (identity(connection) != (APPLICATION_ID, SCHEMA_VERSION)
            or connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]):
        raise ValueError('invalid_host_database')


def initialize(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with closing(connect(root / FILENAME)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        if identity(connection) == (APPLICATION_ID, SCHEMA_VERSION):
            return
        if identity(connection) != (0, 0) or connection.execute('SELECT 1 FROM sqlite_schema LIMIT 1').fetchone():
            raise ValueError('invalid_host_database')
        connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
        connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')


def snapshot(source_root: Path, target_root: Path):
    """Use SQLite's backup API; publish only after validating the complete copy.

    Both backup and restore refuse an existing destination directory. Identity
    configuration and credentials are external to the database and never copied.
    """
    source, target = source_root.resolve() / FILENAME, target_root.resolve()
    with closing(connect(source, readonly=True)) as original:
        if identity(original) != (APPLICATION_ID, SCHEMA_VERSION):
            raise ValueError('invalid_host_database')
        target.mkdir(mode=0o700)
        partial = target / '.snapshot.sqlite3'
        try:
            with closing(connect(partial)) as copy:
                original.backup(copy)
                check(copy)
            partial.replace(target / FILENAME)
        except BaseException:
            partial.unlink(missing_ok=True)
            target.rmdir()
            raise
