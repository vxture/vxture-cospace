"""R1b immutable component files and process-scoped installation exclusion."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import re
import shutil
import sqlite3
import uuid

from packages.data.imports import canonical, sha
from packages.infrastructure.files import bounded_read, relative, safe_path
from packages.service.sample import read_json
from packages.views.agent.local import LocalPackages
from packages.views.agent.runtime import verify, fail


@contextmanager
def installation_lock(path):
    """Never unlink lock files; kernel releases the byte lock on process death."""
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                fail('owner_alive', 'installation is still owned by another process')
            raise
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def write_new(path, content):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


class FilePackages(LocalPackages):
    """Same sample API, independent metadata DB; no automatic legacy migration."""
    def __init__(self, root):
        self.root = safe_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / 'runtime.sqlite3').exists():
            fail('legacy_store', 'use a separate root for files backend; blob migration is not implemented')
        self.path = safe_path(self.root / 'runtime-files.sqlite3')
        with self._connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                fail('unsupported_store', 'unknown files-store schema')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS packages (
                    digest TEXT PRIMARY KEY, package_id TEXT NOT NULL UNIQUE,
                    scene TEXT NOT NULL, manifest BLOB NOT NULL, receipt BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS active (
                    scene TEXT PRIMARY KEY, digest TEXT NOT NULL REFERENCES packages(digest),
                    revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS installs (
                    install_id TEXT PRIMARY KEY, digest TEXT NOT NULL,
                    state TEXT NOT NULL, revision INTEGER NOT NULL, diagnostic TEXT);
                PRAGMA user_version=1;
            ''')

    def _checkpoint(self, phase, install_id):
        """Real-process crash barriers used by validation; production no-op."""

    def _directory(self, digest):
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            fail('invalid_digest', 'package digest must be SHA-256')
        return safe_path(self.root / 'packages' / digest)

    def installation(self, identity):
        if not isinstance(identity, str) or not re.fullmatch('install-[0-9a-f]{32}', identity):
            fail('invalid_installation', 'invalid installation identity')
        with self._connect() as db:
            row = db.execute('SELECT digest,state,revision,diagnostic FROM installs WHERE install_id=?', (identity,)).fetchone()
        if row is None:
            fail('installation_not_found', 'installation missing')
        return {'install_id': identity, 'package_sha256': row[0], 'state': row[1],
                'revision': row[2], 'diagnostic': read_json(row[3]) if row[3] else None}

    def _advance(self, identity, old, new):
        with self._connect() as db:
            result = db.execute('UPDATE installs SET state=?,revision=revision+1 WHERE install_id=? AND state=?',
                                (new, identity, old))
            if result.rowcount != 1:
                fail('state_conflict', 'installation state changed')

    def installations(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 50:
            fail('invalid_limit', 'installation limit must be 1..50')
        with self._connect() as db:
            rows = db.execute('SELECT install_id,digest,state,revision,diagnostic FROM installs ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
        return {'items': [{'install_id': row[0], 'package_sha256': row[1], 'state': row[2],
                           'revision': row[3], 'diagnostic': read_json(row[4]) if row[4] else None} for row in rows]}

    def install(self, package, source):
        package, source = safe_path(package), safe_path(source)
        if any(path.is_relative_to(self.root) or self.root.is_relative_to(path) for path in (package, source)):
            fail('unsafe_path', 'source/package and storage roots must not overlap')
        receipt = verify(package, source)
        raw = bounded_read(package / 'agent-package.json')
        digest = sha(raw)
        if digest != receipt['package_sha256']:
            fail('content_mismatch', 'manifest changed before copying')
        manifest = read_json(raw)
        if shutil.disk_usage(self.root).free < receipt['verified_bytes'] * 3 + 1024 * 1024:
            fail('disk_space', 'insufficient files-store headroom')
        identity = 'install-' + uuid.uuid4().hex
        stage = safe_path(self.root / 'staging' / identity)
        target = self._directory(digest)
        with installation_lock(self.root / 'locks' / (identity + '.lock')):
            with self._connect() as db:
                db.execute('INSERT INTO installs VALUES (?,?,?,0,NULL)', (identity, digest, 'copying'))
            try:
                self._checkpoint('copying', identity)
                stage.mkdir(parents=True, exist_ok=False)
                write_new(stage / 'agent-package.json', raw)
                for item in manifest['components']:
                    ref = item['member']
                    content = bounded_read(package / relative(ref['path']))
                    if len(content) != ref['bytes'] or sha(content) != ref['sha256']:
                        fail('content_mismatch', 'source member changed during copy')
                    write_new(stage / relative(ref['path']), content)
                    self._checkpoint('copied_member', identity)
                staged_receipt = verify(stage, source)
                if staged_receipt != receipt:
                    fail('content_mismatch', 'staged receipt differs from source check')
                self._advance(identity, 'copying', 'verified')
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    stage.rename(target)
                except OSError as error:
                    # Linux reports a populated destination as ENOTEMPTY;
                    # Windows reports EEXIST. Other filesystem errors propagate.
                    if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                        raise
                    # Identical prior orphan may be reused only after full fresh-source verification.
                    if verify(target, source) != receipt:
                        fail('content_corrupt', 'sealed directory differs from fixed input')
                self._checkpoint('sealed_before_state', identity)
                self._advance(identity, 'verified', 'sealed')
                with self._connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT digest FROM packages WHERE package_id=?', (manifest['package_id'],)).fetchone()
                    if row and row[0] != digest:
                        fail('identity_conflict', 'package identity already binds different bytes')
                    if not row:
                        db.execute('INSERT INTO packages VALUES (?,?,?,?,?)',
                                   (digest, manifest['package_id'], manifest['source']['scene_id'], raw, canonical(receipt)))
                    self._load(db, digest)
                    changed = db.execute("UPDATE installs SET state='ready',revision=revision+1 WHERE install_id=? AND state='sealed'", (identity,))
                    if changed.rowcount != 1:
                        fail('state_conflict', 'installation no longer sealed')
                    self._before_commit('install')
                    self._checkpoint('before_commit', identity)
                return {**receipt, 'install_id': identity, 'installation_state': 'ready'}
            except Exception as error:
                with self._connect() as db:
                    db.execute("UPDATE installs SET state='failed',revision=revision+1,diagnostic=? WHERE install_id=? AND state!='ready'",
                               (canonical({'type': type(error).__name__, 'message': str(error)}).decode('utf-8'), identity))
                raise

    def _load(self, db, digest):
        directory = self._directory(digest)
        row = db.execute('SELECT manifest,receipt,package_id,scene FROM packages WHERE digest=?', (digest,)).fetchone()
        if row is None:
            fail('package_not_found', 'package is not registered ready')
        raw, receipt_raw, identity, scene = row
        manifest, receipt = read_json(raw), read_json(receipt_raw)
        if (sha(raw) != digest or bounded_read(directory / 'agent-package.json') != raw
                or receipt['package_sha256'] != digest or receipt['source'] != manifest['source']
                or identity != manifest['package_id'] or scene != manifest['source']['scene_id']):
            fail('content_corrupt', 'registered manifest/receipt/file mismatch')
        members = {}
        for item in manifest['components']:
            ref = item['member']
            content = bounded_read(directory / relative(ref['path']))
            if len(content) != ref['bytes'] or sha(content) != ref['sha256']:
                fail('content_corrupt', 'sealed component digest mismatch')
            members[ref['path']] = content
        return manifest, members

    def recover_installation(self, identity, revision):
        self.installation(identity)  # Validate identity before constructing a lock path.
        if type(revision) is not int or revision < 0:
            fail('invalid_revision', 'revision must be a nonnegative integer')
        with installation_lock(self.root / 'locks' / (identity + '.lock')):
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                result = db.execute("UPDATE installs SET state='interrupted',revision=revision+1,diagnostic=? WHERE install_id=? AND revision=? AND state IN ('copying','verified','sealed')",
                                    (canonical({'code': 'owner_ended', 'message': 'exclusive installation lock obtained; retained files require a fresh install'}).decode('utf-8'), identity, revision))
                if result.rowcount != 1:
                    fail('state_conflict', 'installation cannot be recovered at requested revision')
        return self.installation(identity)
