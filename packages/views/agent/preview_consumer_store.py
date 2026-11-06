"""Small offline preview store. Installed ZIPs and the saved reference commit in SQLite.

One root belongs to one space (None explicitly denotes legacy). Construction never
restores a query session. No network, device permission, or trust grant is involved.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock

from packages.views.agent.preview_consumer import PreviewSession
from packages.views.agent.preview_offline import OfflinePreview, MAX_BYTES

PROFILE = 'cospace.preview-consumer-store/0.1'


def reference(model, digest):
    return {'publication_id': model.publication_id, 'package_sha256': digest,
            'publication_model_manifest_sha256': model.model_hash,
            'model_id': model.manifest['id'], 'frame_id': model.manifest['frame_id'],
            'space_id': model.ownership.get('space_id'),
            'project_id': model.ownership.get('project_id')}


def expected(publication_id, digest, revision=None):
    if not isinstance(publication_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}', publication_id):
        raise ValueError('invalid_publication_id')
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('invalid_package_sha256')
    if revision is not None and (type(revision) is not int or revision < 0):
        raise ValueError('invalid_consumer_revision')


class PersistentPreviewConsumer:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / 'preview-consumer.sqlite3'
        self._lock = RLock()
        self._active = None
        with self._connection() as db:
            row = db.execute('SELECT profile,space_id FROM consumer WHERE id=1').fetchone()
            if db.execute('PRAGMA user_version').fetchone()[0] != 1 or not row or row[0] != PROFILE:
                raise ValueError('unsupported_preview_consumer_store')
            self.space_id = row[1]

    @classmethod
    def initialize(cls, root, space_id=None):
        if space_id is not None and (not isinstance(space_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}', space_id)):
            raise ValueError('invalid_space_id')
        root = Path(root).resolve()
        # Explicit, new root only; never adopt an existing synthetic or preview store.
        root.mkdir(parents=True, exist_ok=False)
        path = root / 'preview-consumer.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('''
                CREATE TABLE packages (
                    digest TEXT PRIMARY KEY, publication TEXT UNIQUE NOT NULL,
                    binding TEXT NOT NULL, data BLOB NOT NULL);
                CREATE TABLE consumer (
                    id INTEGER PRIMARY KEY CHECK(id=1), profile TEXT NOT NULL,
                    space_id TEXT, revision INTEGER NOT NULL CHECK(revision>=0),
                    digest TEXT REFERENCES packages(digest));
                PRAGMA user_version=1;
            ''')
            db.execute('INSERT INTO consumer VALUES (1,?,?,0,NULL)', (PROFILE, space_id))
        return cls(root)

    @contextmanager
    def _connection(self, write=False):
        # Existing-only connections: status/restore must never bootstrap an empty DB.
        db = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            if write:
                db.execute('PRAGMA synchronous=FULL')
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _state(self, db):
        row = db.execute('SELECT revision,digest,space_id,profile FROM consumer WHERE id=1').fetchone()
        if not row or row['profile'] != PROFILE or row['space_id'] != self.space_id:
            raise ValueError('consumer_store_binding_changed')
        revision, digest = row['revision'], row['digest']
        if type(revision) is not int or revision < 0 or ((digest is None) != (revision == 0)):
            raise ValueError('consumer_state_invalid')
        binding = None
        if digest is not None:
            item = db.execute('SELECT publication,binding FROM packages WHERE digest=?', (digest,)).fetchone()
            if not item:
                raise ValueError('installed_package_missing')
            binding = json.loads(item['binding'])
            if (binding.get('package_sha256') != digest or binding.get('publication_id') != item['publication']
                    or binding.get('space_id') != self.space_id):
                raise ValueError('consumer_reference_mismatch')
        return revision, binding

    def status(self):
        with self._lock, self._connection() as db:
            revision, binding = self._state(db)
            session = self._active
            current = reference(session._model, session.package_sha256) if session else None
            return {'profile': PROFILE, 'space_id': self.space_id, 'revision': revision,
                    'saved_reference': binding, 'saved_reference_check': 'metadata_only',
                    'session_reference': current, 'session_revision': session.revision if session else None,
                    'restore_required': binding is not None and (not session or session.revision != revision or current != binding),
                    'quality': 'unverified', 'robot_ready': False}

    def install(self, path, publication_id, package_sha256):
        expected(publication_id, package_sha256)
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        model = OfflinePreview(data, publication_id, package_sha256)
        if model.ownership.get('space_id') != self.space_id:
            raise ValueError('consumer_space_mismatch')
        binding = reference(model, package_sha256)
        with self._connection(write=True) as db:
            self._state(db)
            old = db.execute('SELECT digest FROM packages WHERE publication=?', (publication_id,)).fetchone()
            if old and old['digest'] != package_sha256:
                raise ValueError('publication_package_conflict')
            item = db.execute('SELECT publication FROM packages WHERE digest=?', (package_sha256,)).fetchone()
            if item:
                # Reinstall never silently repairs changed bytes or metadata.
                self._load(db, publication_id, package_sha256)
            else:
                db.execute('INSERT INTO packages VALUES (?,?,?,?)',
                           (package_sha256, publication_id, json.dumps(binding, sort_keys=True), data))
        return {**binding, 'installed': True, 'quality': 'unverified', 'robot_ready': False}

    def packages(self):
        with self._connection() as db:
            self._state(db)
            return [json.loads(row['binding']) for row in db.execute('SELECT binding FROM packages ORDER BY publication')]

    def _load(self, db, publication_id, digest):
        row = db.execute('SELECT publication,binding,length(data) AS size FROM packages WHERE digest=?', (digest,)).fetchone()
        if not row or row['publication'] != publication_id:
            raise ValueError('installed_package_missing_or_mismatch')
        if row['size'] > MAX_BYTES:
            raise ValueError('package_integrity_or_size')
        data = db.execute('SELECT data FROM packages WHERE digest=?', (digest,)).fetchone()['data']
        model = OfflinePreview(data, publication_id, digest)
        if model.ownership.get('space_id') != self.space_id:
            raise ValueError('consumer_space_mismatch')
        if reference(model, digest) != json.loads(row['binding']):
            raise ValueError('consumer_reference_mismatch')
        return model

    def _open(self, publication_id, package_sha256, expected_revision, restore):
        expected(publication_id, package_sha256, expected_revision)
        if type(expected_revision) is not int:
            raise ValueError('invalid_consumer_revision')
        # Serialize CAS across processes; full validation precedes visible state changes.
        with self._lock:
            with self._connection(write=True) as db:
                revision, binding = self._state(db)
                if revision != expected_revision:
                    raise ValueError('consumer_revision_changed')
                if restore and (not binding or binding['publication_id'] != publication_id or binding['package_sha256'] != package_sha256):
                    raise ValueError('saved_reference_mismatch')
                model = self._load(db, publication_id, package_sha256)
                if not restore:
                    revision += 1
                    db.execute('UPDATE consumer SET revision=?,digest=? WHERE id=1', (revision, package_sha256))
                session = PreviewSession(revision, publication_id, package_sha256, model)
            self._active = session
            return session

    def activate(self, publication_id, package_sha256, expected_revision):
        return self._open(publication_id, package_sha256, expected_revision, restore=False)

    def restore(self, publication_id, package_sha256, expected_revision):
        return self._open(publication_id, package_sha256, expected_revision, restore=True)

    def session(self):
        with self._lock:
            if self._active is None:
                raise ValueError('consumer_has_no_active_publication')
            return self._active
