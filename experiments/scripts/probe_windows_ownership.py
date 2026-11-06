"""I4a real Windows process experiment. Does not change production task execution."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid


if os.name != 'nt':
    raise SystemExit('Windows required; no equivalent fallback')
k = c.WinDLL('kernel32', use_last_error=True)
SIZE = c.c_size_t
HANDLE = w.HANDLE


class Basic(c.Structure):
    _fields_ = [('process_time', c.c_longlong), ('job_time', c.c_longlong),
                ('flags', w.DWORD), ('min_ws', SIZE), ('max_ws', SIZE),
                ('active_limit', w.DWORD), ('affinity', SIZE),
                ('priority', w.DWORD), ('scheduling', w.DWORD)]


class IO(c.Structure):
    _fields_ = [(name, c.c_ulonglong) for name in ('ro', 'wo', 'oo', 'rb', 'wb', 'ob')]


class Limits(c.Structure):
    _fields_ = [('basic', Basic), ('io', IO), ('process_memory', SIZE),
                ('job_memory', SIZE), ('peak_process', SIZE), ('peak_job', SIZE)]


class Startup(c.Structure):
    _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR),
                ('title', w.LPWSTR), *[(n, w.DWORD) for n in
                ('x', 'y', 'xs', 'ys', 'xc', 'yc', 'fill', 'flags')],
                ('show', w.WORD), ('reserved_size', w.WORD), ('reserved_ptr', c.c_void_p),
                ('stdin', HANDLE), ('stdout', HANDLE), ('stderr', HANDLE)]


class StartupEx(c.Structure):
    _fields_ = [('startup', Startup), ('attributes', c.c_void_p)]


class Process(c.Structure):
    _fields_ = [('process', HANDLE), ('thread', HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]


def api(name, result, *args):
    fn = getattr(k, name)
    fn.restype, fn.argtypes = result, args
    return fn


close = api('CloseHandle', w.BOOL, HANDLE)
wait = api('WaitForSingleObject', w.DWORD, HANDLE, w.DWORD)
open_process = api('OpenProcess', HANDLE, w.DWORD, w.BOOL, w.DWORD)
get_times = api('GetProcessTimes', w.BOOL, HANDLE, *([c.POINTER(w.FILETIME)] * 4))
create_mutex = api('CreateMutexW', HANDLE, c.c_void_p, w.BOOL, w.LPCWSTR)
release_mutex = api('ReleaseMutex', w.BOOL, HANDLE)
create_job = api('CreateJobObjectW', HANDLE, c.c_void_p, w.LPCWSTR)
set_job = api('SetInformationJobObject', w.BOOL, HANDLE, c.c_int, c.c_void_p, w.DWORD)
init_attrs = api('InitializeProcThreadAttributeList', w.BOOL, c.c_void_p, w.DWORD, w.DWORD, c.POINTER(SIZE))
update_attrs = api('UpdateProcThreadAttribute', w.BOOL, c.c_void_p, w.DWORD, SIZE, c.c_void_p, SIZE, c.c_void_p, c.c_void_p)
delete_attrs = api('DeleteProcThreadAttributeList', None, c.c_void_p)
create_process = api('CreateProcessW', w.BOOL, w.LPCWSTR, w.LPWSTR, c.c_void_p,
                     c.c_void_p, w.BOOL, w.DWORD, c.c_void_p, w.LPCWSTR,
                     c.POINTER(StartupEx), c.POINTER(Process))
resume = api('ResumeThread', w.DWORD, HANDLE)
handle_info = api('GetHandleInformation', w.BOOL, HANDLE, c.POINTER(w.DWORD))
in_job = api('IsProcessInJob', w.BOOL, HANDLE, HANDLE, c.POINTER(w.BOOL))
get_exit = api('GetExitCodeProcess', w.BOOL, HANDLE, c.POINTER(w.DWORD))


def checked(value):
    if not value:
        raise c.WinError(c.get_last_error())
    return value


def identity(handle, pid):
    times = [w.FILETIME() for _ in range(4)]
    checked(get_times(handle, *(c.byref(t) for t in times)))
    return {'pid': pid, 'creation_ticks': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime}


def write(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    tmp.replace(path)


def until(predicate, seconds=12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.02)
    raise TimeoutError('experiment checkpoint timed out')


def spawn(root, job, executable):
    size = SIZE()
    init_attrs(None, 1, 0, c.byref(size))
    buf = c.create_string_buffer(size.value)
    checked(init_attrs(buf, 1, 0, c.byref(size)))
    try:
        jobs = (HANDLE * 1)(job)
        # PROC_THREAD_ATTRIBUTE_JOB_LIST: assignment is part of process creation.
        checked(update_attrs(buf, 0, 0x0002000D, jobs, c.sizeof(jobs), None, None))
        startup = StartupEx()
        startup.startup.cb = c.sizeof(startup)
        startup.attributes = c.cast(buf, c.c_void_p)
        process = Process()
        command = c.create_unicode_buffer(subprocess.list2cmdline(
            [executable, str(Path(__file__).resolve()), '--mode', 'worker', '--root', str(root)]))
        checked(create_process(executable, command, None, None, False,
                               0x00080000 | 0x00000004 | 0x08000000,
                               None, str(Path.cwd()), c.byref(startup), c.byref(process)))
        return process
    finally:
        delete_attrs(buf)


def supervise(root, stage, mutex_name):
    mutex = checked(create_mutex(None, False, mutex_name))
    checked(wait(mutex, 0) == 0)
    job = checked(create_job(None, None))
    process = None
    try:
        limits = Limits()
        limits.basic.flags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE, ACTIVE_PROCESS
        limits.basic.active_limit = 1
        checked(set_job(job, 9, c.byref(limits), c.sizeof(limits)))
        flags = w.DWORD()
        checked(handle_info(job, c.byref(flags)))
        assert not flags.value & 1, 'job handle inherited'
        if stage == 'before_spawn':
            write(root / 'checkpoint.json', {'stage': stage})
            time.sleep(60)
        venv_python = Path(__file__).resolve().parents[2] / '.venv' / 'Scripts' / 'python.exe'
        process = spawn(root, job, str(venv_python) if stage == 'venv_launcher' else sys._base_executable)
        member = w.BOOL()
        checked(in_job(process.process, job, c.byref(member)))
        assert member.value
        record = {'supervisor': identity(k.GetCurrentProcess(), os.getpid()),
                  'child': identity(process.process, process.pid), 'job_attached': True,
                  'job_handle_inheritable': False}
        # Harness observation is separate from the simulated durable registration.
        write(root / 'observed.json', record)
        if stage == 'created':
            write(root / 'checkpoint.json', {'stage': stage})
            time.sleep(60)
        write(root / 'registered.json', record)
        if stage == 'registered':
            write(root / 'checkpoint.json', {'stage': stage})
            time.sleep(60)
        assert resume(process.thread) != 0xFFFFFFFF
        until(lambda: (root / 'ready.json').exists() or wait(process.process, 0) == 0)
        if stage == 'venv_launcher':
            assert not (root / 'ready.json').exists(), 'launcher unexpectedly supported active-process limit'
            code = w.DWORD()
            checked(get_exit(process.process, c.byref(code)))
            write(root / 'launcher_exit.json', {'code': code.value, 'ready': False})
            write(root / 'checkpoint.json', {'stage': stage})
            time.sleep(60)
        assert (root / 'ready.json').exists(), 'worker exited before readiness'
        write(root / 'permit.json', {'allowed': True})
        until(lambda: (root / 'running.json').exists())
        if stage == 'running':
            write(root / 'checkpoint.json', {'stage': stage})
            time.sleep(60)
        if stage == 'worker_exit':
            write(root / 'exit.json', {})
            assert wait(process.process, 5000) == 0
            write(root / 'checkpoint.json', {'stage': stage})
            time.sleep(60)
        write(root / 'exit.json', {})
        assert wait(process.process, 5000) == 0
    finally:
        close(job)
        if process:
            close(process.thread)
            close(process.process)
        release_mutex(mutex)
        close(mutex)


def worker(root):
    write(root / 'ready.json', {'pid': os.getpid()})
    until(lambda: (root / 'permit.json').exists())
    try:
        extra = subprocess.Popen([sys.executable, '-c', 'pass'])
    except OSError as error:
        write(root / 'descendant_denied.json', {'winerror': error.winerror})
    else:
        extra.wait(timeout=5)
        raise AssertionError('job allowed a descendant process')
    write(root / 'running.json', {'pid': os.getpid()})
    until(lambda: (root / 'exit.json').exists(), 60)


def harness(root):
    root.mkdir(parents=True, exist_ok=False)
    results = []
    for stage in ('before_spawn', 'created', 'registered', 'running', 'worker_exit', 'normal', 'venv_launcher'):
        case = root / stage
        case.mkdir()
        name = 'Local\\CoSpaceProbe-' + uuid.uuid4().hex
        command = [sys._base_executable, str(Path(__file__).resolve()), '--mode', 'supervisor',
                   '--root', str(case), '--stage', stage, '--mutex', name]
        child_handle = mutex = None
        with (case / 'supervisor.log').open('w', encoding='utf-8') as log:
            parent = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                if stage == 'before_spawn':
                    until(lambda: (case / 'checkpoint.json').exists())
                    mutex = checked(create_mutex(None, False, name))
                    assert wait(mutex, 0) == 258
                    parent.kill()
                    parent.wait(timeout=12)
                    assert wait(mutex, 5000) in (0, 0x80)
                    checked(release_mutex(mutex))
                    assert not (case / 'observed.json').exists()
                    results.append({'stage': stage, 'passed': True, 'child_created': False})
                    continue
                until(lambda: (case / 'observed.json').exists() or parent.poll() is not None)
                assert parent.poll() is None, 'supervisor failed; inspect log'
                record = json.loads((case / 'observed.json').read_text())
                assert record['supervisor']['pid'] == parent.pid, 'must kill supervisor directly, not a launcher'
                child_handle = checked(open_process(0x100000 | 0x1000, False, record['child']['pid']))
                actual = identity(child_handle, record['child']['pid'])
                assert actual == record['child']
                assert actual != {**actual, 'creation_ticks': actual['creation_ticks'] + 1}
                mutex = checked(create_mutex(None, False, name))
                assert wait(mutex, 0) == 258, 'live supervisor must hold lock'
                if stage != 'normal':
                    until(lambda: (case / 'checkpoint.json').exists())
                    assert wait(mutex, 0) == 258, 'owner lock must survive worker exit'
                    if stage in ('created', 'registered'):
                        assert not (case / 'ready.json').exists(), 'suspended child ran'
                    parent.kill()
                exit_code = parent.wait(timeout=12)
                if stage == 'normal':
                    assert exit_code == 0, 'normal supervisor failed'
                assert wait(child_handle, 5000) == 0, 'child survived owner death'
                lock_result = wait(mutex, 5000)
                assert lock_result in (0, 0x80), 'lock not released'
                checked(release_mutex(mutex))
                if stage in ('running', 'worker_exit', 'normal'):
                    assert (case / 'descendant_denied.json').exists()
                results.append({'stage': stage, 'passed': True, 'identity': record,
                                'child_exited': True, 'lock_after_exit': lock_result,
                                'registered': (case / 'registered.json').exists()})
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=12)
                if child_handle:
                    close(child_handle)
                if mutex:
                    close(mutex)
    write(root / 'results.json', {'scope': 'I4a prototype, not production recovery',
          'python': platform.python_version(), 'windows': platform.platform(),
          'worker_python': sys._base_executable,
          'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases': results})
    print(f'{len(results)} real-process cases passed; evidence: {root}')


if __name__ == '__main__':
    # Pseudo-handle must be pointer-sized on 64-bit Windows.
    api('GetCurrentProcess', HANDLE)
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('harness', 'supervisor', 'worker'), default='harness')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--stage', default='normal')
    parser.add_argument('--mutex', default='')
    args = parser.parse_args()
    if args.mode == 'harness':
        harness(args.root.resolve())
    elif args.mode == 'supervisor':
        supervise(args.root, args.stage, args.mutex)
    else:
        worker(args.root)
