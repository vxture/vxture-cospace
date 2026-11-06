"""Windows-only J1 lock/control prototype. No validity proofs or recovery release."""
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import math
import os
import re
import sqlite3
import time
import uuid

from packages.infrastructure.files import safe_path


class LockError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Overlapped(c.Structure):
    _fields_ = [('internal', c.c_size_t), ('internal_high', c.c_size_t),
                ('offset', w.DWORD), ('offset_high', w.DWORD), ('event', w.HANDLE)]


class FileInfo(c.Structure):
    _fields_ = [('attributes', w.DWORD), ('created', w.FILETIME), ('accessed', w.FILETIME),
                ('written', w.FILETIME), ('volume', w.DWORD), ('size_high', w.DWORD),
                ('size_low', w.DWORD), ('links', w.DWORD), ('index_high', w.DWORD), ('index_low', w.DWORD)]


def native():
    if os.name != 'nt':
        raise LockError('windows_required')
    kernel = c.WinDLL('kernel32', use_last_error=True)
    definitions = {
        'CreateFileW': (w.HANDLE, [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]),
        'GetFileInformationByHandle': (w.BOOL, [w.HANDLE, c.POINTER(FileInfo)]),
        'LockFileEx': (w.BOOL, [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, w.DWORD, c.POINTER(Overlapped)]),
        'UnlockFileEx': (w.BOOL, [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, c.POINTER(Overlapped)]),
        'CloseHandle': (w.BOOL, [w.HANDLE])}
    for name, (result, args) in definitions.items():
        function = getattr(kernel, name)
        function.restype, function.argtypes = result, args
    return kernel


class StableLock:
    def __init__(self, path):
        self.path = safe_path(path)
        self.kernel = native()

    def _open(self, create):
        safe_path(self.path)
        # Share read/write but not deletion; no inheritable security attributes.
        handle = self.kernel.CreateFileW(str(self.path), 0xC0000000, 3, None,
                                         1 if create else 3, 0x00200080, None)
        if handle == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        try:
            info = FileInfo()
            if not self.kernel.GetFileInformationByHandle(handle, c.byref(info)):
                raise c.WinError(c.get_last_error())
            if info.attributes & (0x400 | 0x10) or info.links != 1:
                raise LockError('unsafe_lock_file')
            identity = f'{info.volume:08x}:{info.index_high:08x}{info.index_low:08x}'
            return handle, identity
        except BaseException:
            self.kernel.CloseHandle(handle)
            raise

    @contextmanager
    def hold(self, timeout=1, *, create=False):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 5:
            raise LockError('invalid_timeout')
        handle, identity = self._open(create)
        locked = False
        overlap = Overlapped()  # Same offset 0 and length 1 in every participant.
        deadline = time.monotonic() + timeout
        try:
            while True:
                if self.kernel.LockFileEx(handle, 3, 0, 1, 0, c.byref(overlap)):
                    locked = True
                    break
                code = c.get_last_error()
                if code != 33:  # ERROR_LOCK_VIOLATION only; other failures are not busy.
                    raise c.WinError(code)
                if time.monotonic() >= deadline:
                    raise LockError('busy')
                time.sleep(min(.01, max(0, deadline - time.monotonic())))
            yield identity
        finally:
            try:
                if locked and not self.kernel.UnlockFileEx(handle, 0, 1, 0, c.byref(overlap)):
                    raise c.WinError(c.get_last_error())
            finally:
                self.kernel.CloseHandle(handle)


class ControlProbe:
    """Independent toy control table; never opens validity-test.sqlite3 or v2 data."""
    def __init__(self, root, context, timeout=1):
        self.root = safe_path(root)
        self.path = safe_path(self.root / 'ownership-test.sqlite3')
        self.lock = StableLock(self.root / 'ownership.lock')
        if not isinstance(context, str) or not re.fullmatch('[0-9a-f]{64}', context):
            raise LockError('invalid_context')
        self.context, self.timeout = context, timeout
        with self.lock.hold(timeout) as identity, self._db() as db:
            row = self._read(db, identity)
            self.store_id, self.generation = row[0], row[2]

    @classmethod
    def bootstrap(cls, root, context):
        native()
        if not isinstance(context, str) or not re.fullmatch('[0-9a-f]{64}', context):
            raise LockError('invalid_context')
        root = safe_path(root)
        root.mkdir(parents=True, exist_ok=False)
        lock = StableLock(root / 'ownership.lock')
        with lock.hold(create=True) as identity:
            path = safe_path(root / 'ownership-test.sqlite3')
            with path.open('xb'):
                pass
            db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)
            try:
                db.execute('PRAGMA synchronous=FULL')
                with db:
                    db.execute('CREATE TABLE control (store_id TEXT NOT NULL, context TEXT NOT NULL, generation INTEGER NOT NULL, mode TEXT NOT NULL, lock_identity TEXT NOT NULL, writes INTEGER NOT NULL)')
                    db.execute('INSERT INTO control VALUES (?,?,1,?,?,0)', (str(uuid.uuid4()), context, 'normal', identity))
                    db.execute('PRAGMA user_version=1')
            finally:
                db.close()
        return cls(root, context)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(safe_path(self.path).as_uri() + '?mode=rw', uri=True, timeout=1)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def _read(self, db, lock_identity):
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise LockError('unsupported_control')
        rows = db.execute('SELECT store_id,context,generation,mode,lock_identity,writes FROM control LIMIT 2').fetchall()
        if len(rows) != 1:
            raise LockError('invalid_control')
        row = rows[0]
        if (not isinstance(row[0], str) or not re.fullmatch('[0-9a-f-]{36}', row[0])
                or type(row[2]) is not int or not 1 <= row[2] <= 9007199254740991
                or row[3] not in ('normal', 'recovering') or type(row[5]) is not int or row[5] < 0):
            raise LockError('invalid_control')
        if row[1] != self.context:
            raise LockError('context_changed')
        if row[4] != lock_identity:
            raise LockError('lock_identity_changed')
        return row

    def operation(self, action='query'):
        if action not in ('query', 'write', 'begin_recovery'):
            raise LockError('unsupported_action')
        with self.lock.hold(self.timeout) as identity, self._db() as db:
            db.execute('BEGIN IMMEDIATE' if action != 'query' else 'BEGIN')
            row = self._read(db, identity)
            if row[0] != self.store_id:
                raise LockError('store_changed')
            if row[2] != self.generation:
                raise LockError('stale_generation')
            if row[3] != 'normal':
                raise LockError('recovery_required')
            if action == 'begin_recovery':
                if row[2] == 9007199254740991:
                    raise LockError('generation_exhausted')
                db.execute('UPDATE control SET generation=generation+1,mode=?', ('recovering',))
            elif action == 'write':
                db.execute('UPDATE control SET writes=writes+1')
            return {'probe_only': True, 'authorized': False, 'robot_ready': False,
                    'observed_generation': row[2], 'action': action}
