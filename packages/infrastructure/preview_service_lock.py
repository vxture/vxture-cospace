"""Exclusive process lifetime guard shared by local servers and cold backups."""
from contextlib import contextmanager
from pathlib import Path
import os


@contextmanager
def service_guard(runtime, *, require_existing=False):
    root=Path(runtime).resolve()
    path=root/'.preview-service.lock'
    if require_existing and not path.is_file():
        raise ValueError('managed_service_lock_required')
    root.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        if path.stat().st_size==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('stop_managed_service_before_backup_or_second_start') from exc
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream,fcntl.LOCK_UN)
