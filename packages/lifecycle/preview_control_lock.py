"""Cooperative, reentrant runtime mutation lock (thread + local process boundary)."""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import os
import threading
import time

_registry={}
_registry_lock=threading.Lock()

@contextmanager
def mutation_guard(runtime):
    path=(Path(runtime).resolve()/'.preview-mutation.lock')
    with _registry_lock:
        lock,local=_registry.setdefault(str(path),(threading.RLock(),threading.local()))
    with lock:
        if getattr(local,'depth',0):
            local.depth+=1
            try:yield
            finally:local.depth-=1
            return
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a+b') as stream:
            if path.stat().st_size==0:stream.write(b'0');stream.flush()
            deadline=time.monotonic()+15
            while True:
                try:
                    stream.seek(0)
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic()>=deadline:raise ValueError('lifecycle_runtime_busy_refresh_required') from exc
                    time.sleep(.025)
            local.depth=1
            try:yield
            finally:
                local.depth=0;stream.seek(0)
                if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(stream,fcntl.LOCK_UN)

def serialized(runtime_of):
    def decorate(function):
        @wraps(function)
        def call(*args,**kwargs):
            with mutation_guard(runtime_of(args[0])):return function(*args,**kwargs)
        return call
    return decorate
