"""J1 real-process Windows harness; independent synthetic control, no recovery release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import sqlite3
import subprocess
import sys
import threading
import time

from experiments.scripts.recovery_lock_probe import ControlProbe, StableLock, LockError

REPO = Path(__file__).resolve().parents[2]
CONTEXT = 'a' * 64


def emit(value):
    print(json.dumps({'pid': os.getpid(), **value}), flush=True)


def actor(args):
    if args.actor == 'hold':
        with StableLock(Path(args.root) / 'ownership.lock').hold(args.timeout) as identity:
            emit({'held': True, 'lock_identity': identity})
            sys.stdin.readline()
        emit({'released': True})
        return
    if args.actor == 'acquire':
        try:
            with StableLock(Path(args.root) / 'ownership.lock').hold(args.timeout) as identity:
                emit({'acquired': True, 'lock_identity': identity})
        except LockError as error:
            emit({'error': error.code})
        return
    probe = ControlProbe(args.root, CONTEXT)
    emit({'opened': True, 'generation': probe.generation, 'store_id': probe.store_id})
    for line in sys.stdin:
        action = line.strip()
        if action == 'exit':
            return
        try:
            emit(probe.operation(action))
        except LockError as error:
            emit({'error': error.code})


class Child:
    def __init__(self, root, mode, timeout=.15, cwd=None):
        # Spawn the real interpreter, avoiding the Windows venv launcher PID indirection.
        paths = [str(REPO), str(Path(sys.prefix) / 'Lib/site-packages')]
        code = 'import sys,runpy;sys.path[:0]=' + repr(paths) + ";runpy.run_module('experiments.scripts.check_recovery_lock',run_name='__main__')"
        self.process = subprocess.Popen([sys._base_executable, '-c', code, '--actor', mode,
            '--root', str(root), '--timeout', str(timeout)], cwd=cwd or REPO,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        self.messages = queue.Queue()
        def read():
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
            self.messages.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def receive(self):
        value = self.messages.get(timeout=10)
        if value is None:
            raise AssertionError('child exited: ' + self.process.stderr.read())
        assert value['pid'] == self.process.pid, 'launcher indirection: do not kill an unowned PID'
        return value

    def send(self, value):
        self.process.stdin.write(value + '\n')
        self.process.stdin.flush()

    def kill(self):
        self.process.kill()
        self.process.wait(timeout=10)

    def finish(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()
        self.reader.join(timeout=2)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.finish()


def acquire(root):
    with Child(root, 'acquire') as contender:
        result = contender.receive()
        assert contender.process.wait(timeout=10) == 0
        return result


def normal_exit(root):
    ControlProbe.bootstrap(root, CONTEXT)
    with Child(root, 'hold') as owner:
        held = owner.receive()
        assert held['held']
        denied = acquire(root)
        assert denied['error'] == 'busy' and owner.process.poll() is None
        owner.send('release')
        assert owner.receive()['released']
        assert owner.process.wait(timeout=10) == 0
    after = acquire(root)
    assert after['acquired'] and after['lock_identity'] == held['lock_identity']
    return {'holder': held, 'contender': denied, 'after_exit': after}


def killed_owner(root):
    ControlProbe.bootstrap(root, CONTEXT)
    with Child(root, 'hold') as owner:
        held = owner.receive()
        assert acquire(root)['error'] == 'busy'
        owner.kill()
    after = acquire(root)
    assert after['acquired'] and after['lock_identity'] == held['lock_identity']
    return {'holder': held, 'after_kill': after}


def live_owner_and_file_replacement(root):
    ControlProbe.bootstrap(root, CONTEXT)
    path = root / 'ownership.lock'
    replacement = root / 'replacement.lock'
    replacement.write_bytes(b'replacement')
    with Child(root, 'hold') as owner:
        held = owner.receive()
        os.utime(path, (1, 1))  # Ancient mtime does not authorize takeover.
        assert acquire(root)['error'] == 'busy'
        assert acquire(root)['error'] == 'busy' and owner.process.poll() is None
        failures = []
        for operation in (lambda: path.unlink(), lambda: os.replace(replacement, path)):
            try:
                operation()
            except OSError as error:
                failures.append(error.winerror)
            else:
                raise AssertionError('live lock file was removed/replaced')
        assert path.exists() and replacement.exists()
        owner.send('release')
        assert owner.receive()['released']
        assert owner.process.wait(timeout=10) == 0
    return {'holder': held, 'delete_replace_winerrors': failures, 'old_mtime_did_not_transfer_ownership': True}


def aliases(root):
    ControlProbe.bootstrap(root, CONTEXT)
    relative = os.path.relpath(root, root.parent)
    with Child(relative, 'hold', cwd=root.parent) as owner:
        held = owner.receive()
        absolute = acquire(str(root).upper())
        assert absolute['error'] == 'busy'
        owner.send('release')
        assert owner.receive()['released']
        assert owner.process.wait(timeout=10) == 0
    return {'relative_holder': held, 'absolute_case_alias': absolute}


def old_generation(root):
    ControlProbe.bootstrap(root, CONTEXT)
    with Child(root, 'session') as old:
        opened = old.receive()
        old.send('query')
        assert not old.receive()['authorized']
        current = ControlProbe(root, CONTEXT)
        current.operation('begin_recovery')
        observed = []
        for operation in ('query', 'write', 'begin_recovery'):
            old.send(operation)
            result = old.receive()
            assert result['error'] == 'stale_generation'
            observed.append(result)
        old.send('exit')
        assert old.process.wait(timeout=10) == 0
    fresh = ControlProbe(root, CONTEXT)
    assert fresh.generation == 2
    try:
        fresh.operation('query')
    except LockError as error:
        assert error.code == 'recovery_required'
    else:
        raise AssertionError('fresh object bypassed recovering mode')
    with sqlite3.connect(fresh.path) as db:
        assert db.execute('SELECT writes FROM control').fetchone() == (0,)
    return {'old_object': opened, 'stale_results': observed, 'fresh_generation': 2, 'fresh_query': 'recovery_required'}


def recovery_process_exit(root):
    ControlProbe.bootstrap(root, CONTEXT)
    with Child(root, 'session') as recovery:
        opened = recovery.receive()
        recovery.send('begin_recovery')
        assert recovery.receive()['action'] == 'begin_recovery'
        recovery.kill()
    fresh = ControlProbe(root, CONTEXT)
    assert fresh.generation == 2
    try:
        fresh.operation('write')
    except LockError as error:
        assert error.code == 'recovery_required'
    else:
        raise AssertionError('owner exit cleared durable recovering mode')
    return {'owner': opened, 'reopened_generation': 2, 'mode_survives_owner_exit': True}


def competing_recoveries(root):
    ControlProbe.bootstrap(root, CONTEXT)
    with Child(root, 'session') as first, Child(root, 'session') as second:
        opened = [first.receive(), second.receive()]
        assert all(item['generation'] == 1 for item in opened)
        first.send('begin_recovery')
        second.send('begin_recovery')
        results = [first.receive(), second.receive()]
        assert sum(item.get('action') == 'begin_recovery' for item in results) == 1
        assert sum(item.get('error') == 'stale_generation' for item in results) == 1
    assert ControlProbe(root, CONTEXT).generation == 2
    return {'opened': opened, 'results': results, 'generation': 2}


def replaced_lock_identity(root):
    probe = ControlProbe.bootstrap(root, CONTEXT)
    replacement = root / 'replacement.lock'
    replacement.write_bytes(b'new identity')
    os.replace(replacement, root / 'ownership.lock')
    for operation in (lambda: probe.operation('write'), lambda: ControlProbe(root, CONTEXT)):
        try:
            operation()
        except LockError as error:
            assert error.code == 'lock_identity_changed'
        else:
            raise AssertionError('replacement lock identity accepted')
    return {'old_and_new_objects': 'lock_identity_changed'}


def hardlink_rejected(root):
    probe = ControlProbe.bootstrap(root, CONTEXT)
    os.link(root / 'ownership.lock', root / 'alias.lock')
    try:
        probe.operation('query')
    except LockError as error:
        assert error.code == 'unsafe_lock_file'
    else:
        raise AssertionError('hard-linked lock accepted')
    return {'actual_hardlink': 'unsafe_lock_file'}


def lost_database(root):
    probe = ControlProbe.bootstrap(root, CONTEXT)
    probe.path.unlink()  # Controlled fault in this newly created test-only directory.
    try:
        probe.operation('query')
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError('missing control database recreated')
    assert not probe.path.exists()
    return {'missing_database_recreated': False}


def junction_rejected(root):
    root.mkdir()
    target, link = root / 'target', root / 'junction'
    ControlProbe.bootstrap(target, CONTEXT)
    result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)],
                            capture_output=True, timeout=10)
    assert result.returncode == 0, 'test junction could not be created'
    try:
        assert link.is_junction()
        try:
            ControlProbe(link, CONTEXT)
        except ValueError as error:
            assert getattr(error, 'code', None) == 'unsafe_path'
        else:
            raise AssertionError('junction store path accepted')
    finally:
        # Remove only this newly created junction, never its target tree.
        assert link.parent == root and link.is_junction()
        link.rmdir()
    assert (target / 'ownership-test.sqlite3').is_file()
    return {'actual_directory_junction': 'unsafe_path', 'target_preserved': True}


CASES = {'normal_exit': normal_exit, 'killed_owner': killed_owner,
         'live_owner_and_file_replacement': live_owner_and_file_replacement,
         'path_aliases': aliases, 'old_generation': old_generation,
         'recovery_process_exit': recovery_process_exit,
         'competing_recoveries': competing_recoveries,
         'replaced_lock_identity': replaced_lock_identity, 'hardlink_rejected': hardlink_rejected,
         'lost_database': lost_database, 'junction_rejected': junction_rejected}


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, operation in CASES.items():
        started = time.monotonic()
        detail = operation(output / name)
        results.append({'case': name, 'passed': True, 'seconds': time.monotonic() - started, 'detail': detail})
        print(name + ': passed', flush=True)
    sources = [Path(__file__).resolve(), Path(__file__).with_name('recovery_lock_probe.py'), REPO / 'tests/test_recovery_lock.py']
    report = {'scope': 'J1 standalone Windows lock/control prototype', 'cases': results,
              'python': platform.python_version(), 'platform': platform.platform(),
              'child_interpreter': sys._base_executable, 'authorized': False, 'robot_ready': False,
              'validity_runtime_integrated': False, 'physical_power_loss_tested': False,
              'source_sha256': {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--actor', choices=('hold', 'acquire', 'session'))
    parser.add_argument('--timeout', type=float, default=.15)
    args = parser.parse_args()
    if args.actor:
        actor(args)
    else:
        run(Path(args.root).absolute())
