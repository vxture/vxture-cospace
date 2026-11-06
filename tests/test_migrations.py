"""Versioned setup and non-destructive migration behavior on isolated databases."""
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import create_engine, inspect, text

from packages.infrastructure.migrations import migrate_database


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine('sqlite:///' + str(Path(self.temp.name) / 'migration.db'))
        self.addCleanup(self.engine.dispose)

    def test_repeat_upgrade_and_empty_downgrade(self):
        migrate_database(self.engine)
        migrate_database(self.engine)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('select version_num from alembic_version')).scalar_one(),
                             '0003_check_jobs')
        migrate_database(self.engine, 'downgrade')
        self.assertNotIn('cospace_sample_scenes', inspect(self.engine).get_table_names())
        migrate_database(self.engine)
        self.assertIn('cospace_sample_scenes', inspect(self.engine).get_table_names())

    def test_populated_downgrade_refused_and_data_survives(self):
        migrate_database(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("insert into cospace_sample_scenes values ('keep', NULL, 0)"))
        with self.assertRaisesRegex(RuntimeError, 'downgrade refused'):
            migrate_database(self.engine, 'downgrade')
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('select scene_id from cospace_sample_scenes')).scalar_one(), 'keep')
        migrate_database(self.engine)
