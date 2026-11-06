"""R1a local synthetic reference store, not a robot SDK or validity authority."""
import json
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from packages.data.imports import canonical, sha
from packages.infrastructure.files import bounded_read, relative, safe_path
from packages.service.sample import read_json
from packages.spatial.coverage import query_coverage
from packages.views.agent.runtime import verify, fail


class LocalSession:
    def __init__(self, manifest, members, revision):
        self._manifest = manifest
        self._revision = revision
        coverage = next(item for item in manifest['components'] if item['role'] == 'occupancy')
        self._coverage = read_json(members[coverage['member']['path']])
        self._closed = False

    def query(self, point):
        if self._closed:
            fail('session_closed', 'session has been closed')
        return {'package_id': self._manifest['package_id'], 'source': dict(self._manifest['source']),
                'revision': self._revision, 'validity': 'unverified_sample_only',
                'robot_ready': False, **query_coverage(self._coverage, point)}

    def close(self):
        self._closed = True
        self._coverage = None


class LocalPackages:
    """SQLite blobs are bounded synthetic fixtures; large-map storage is deferred."""
    def __init__(self, root):
        self.root = safe_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / 'runtime-files.sqlite3').exists():
            fail('files_store', 'use files backend for this root')
        self.path = safe_path(self.root / 'runtime.sqlite3')
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS packages (
                    digest TEXT PRIMARY KEY, package_id TEXT NOT NULL UNIQUE,
                    scene TEXT NOT NULL, manifest BLOB NOT NULL, members BLOB NOT NULL,
                    receipt BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS active (
                    scene TEXT PRIMARY KEY, digest TEXT NOT NULL REFERENCES packages(digest),
                    revision INTEGER NOT NULL);
            ''')

    @contextmanager
    def _connect(self):
        safe_path(self.path)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _before_commit(self, operation):
        """Fault-injection barrier for transaction/crash verification."""

    def install(self, package, source):
        package = safe_path(package)
        # Copy first, then validate copied bytes. Nothing is visible until COMMIT.
        raw = bounded_read(package / 'agent-package.json')
        # Validate the original before using its paths; staged copy is verified again.
        verify(package, source)
        manifest = read_json(raw)
        expected = len(raw) + sum(item['member']['bytes'] for item in manifest['components'])
        if shutil.disk_usage(self.root).free < expected * 3 + 1024 * 1024:
            fail('disk_space', 'insufficient reference-store installation headroom')
        with tempfile.TemporaryDirectory(prefix='stage-', dir=self.root) as temporary:
            stage = Path(temporary)
            (stage / 'agent-package.json').write_bytes(raw)
            members = {}
            for item in manifest['components']:
                name = str(relative(item['member']['path']))
                content = bounded_read(package / name)
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                members[name] = content.decode('utf-8')
            receipt = verify(stage, source)
        digest = receipt['package_sha256']
        try:
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT digest FROM packages WHERE package_id=?',
                                 (manifest['package_id'],)).fetchone()
                if row:
                    if row[0] != digest:
                        fail('identity_conflict', 'package identity already binds different bytes')
                    self._load(db, digest)
                    return receipt
                db.execute('INSERT INTO packages VALUES (?,?,?,?,?,?)',
                           (digest, manifest['package_id'], manifest['source']['scene_id'],
                            raw, canonical(members), canonical(receipt)))
                self._before_commit('install')
            return receipt
        except sqlite3.IntegrityError as error:
            fail('identity_conflict', str(error))

    def _load(self, db, digest):
        row = db.execute('SELECT manifest,members,receipt,package_id,scene FROM packages WHERE digest=?',
                         (digest,)).fetchone()
        if row is None:
            fail('package_not_found', 'installed package missing')
        raw, payload, receipt_raw, identity, scene = row
        manifest, members, receipt = read_json(raw), read_json(payload), read_json(receipt_raw)
        if (sha(raw) != digest or receipt['package_sha256'] != digest
                or receipt['source'] != manifest['source'] or manifest['package_id'] != identity
                or manifest['source']['scene_id'] != scene):
            fail('content_corrupt', 'installed manifest or receipt mismatch')
        for item in manifest['components']:
            ref = item['member']
            if ref['path'] not in members:
                fail('content_corrupt', 'installed member missing')
            content = members[ref['path']].encode('utf-8')
            if len(content) != ref['bytes'] or sha(content) != ref['sha256']:
                fail('content_corrupt', 'installed member digest mismatch')
        return manifest, members

    def status(self, scene):
        with self._connect() as db:
            row = db.execute('SELECT digest,revision FROM active WHERE scene=?', (scene,)).fetchone()
            if row is None:
                return {'scene_id': scene, 'revision': 0, 'package_sha256': None}
            manifest, _ = self._load(db, row[0])
            return {'scene_id': scene, 'revision': row[1], 'package_sha256': row[0],
                    'package_id': manifest['package_id'], 'validity': 'unverified_sample_only', 'robot_ready': False}

    def activate(self, scene, digest, revision):
        if type(revision) is not int or revision < 0:
            fail('invalid_revision', 'revision must be a nonnegative integer')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            manifest, _ = self._load(db, digest)
            if manifest['source']['scene_id'] != scene:
                fail('scene_mismatch', 'package belongs to another scene')
            row = db.execute('SELECT revision FROM active WHERE scene=?', (scene,)).fetchone()
            current = row[0] if row else 0
            if revision != current:
                fail('state_conflict', 'active revision changed')
            db.execute('INSERT INTO active VALUES (?,?,?) ON CONFLICT(scene) DO UPDATE SET digest=excluded.digest,revision=excluded.revision',
                       (scene, digest, current + 1))
            self._before_commit('activate')
        return {'scene_id': scene, 'package_sha256': digest, 'revision': current + 1,
                'validity': 'unverified_sample_only', 'robot_ready': False}

    def open_session(self, scene):
        with self._connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT digest,revision FROM active WHERE scene=?', (scene,)).fetchone()
            if row is None:
                fail('no_active_package', 'no package active for scene')
            manifest, members = self._load(db, row[0])
            return LocalSession(manifest, members, row[1])
