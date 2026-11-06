"""I4a fixed-worker environment probe; no database or production recovery writes."""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
# -I deliberately excludes both CWD and the script directory from imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_windows_ownership as win


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bootstrap(root):
    try:
        binding = json.loads((root / 'binding.json').read_text(encoding='utf-8'))
        if Path(sys.prefix).resolve() != Path(binding['venv']).resolve():
            raise ValueError('venv_prefix_mismatch')
        for key in ('base_python', 'venv_config', 'lock', 'bootstrap', 'ownership_probe'):
            if digest(binding[key]['path']) != binding[key]['sha256']:
                raise ValueError('bound_file_changed:' + key)
        sys.path.insert(0, str(REPO))
        from packages.infrastructure.runner import LocalRunner
        if LocalRunner(None).fingerprint() != binding['fingerprint']:
            raise ValueError('runtime_fingerprint_mismatch')
        import jsonschema
        from importlib.metadata import distribution
        origins = {}
        for name in ('jsonschema', 'sqlalchemy', 'psycopg', 'alembic'):
            origin = Path(distribution(name).locate_file('')).resolve()
            if not origin.is_relative_to(Path(sys.prefix).resolve()):
                raise ValueError('dependency_outside_venv:' + name)
            origins[name] = str(origin)
        win.write(root / 'environment.json', {'pid': os.getpid(), 'prefix': sys.prefix,
                  'base_prefix': sys.base_prefix, 'executable': sys.executable,
                  'base_executable': sys._base_executable, 'origins': origins,
                  'jsonschema': jsonschema.__file__, 'fingerprint': binding['fingerprint'],
                  'pythonpath_present': 'PYTHONPATH' in os.environ,
                  'db_url_present': 'COSPACE_DATABASE_URL' in os.environ})
        import apps.worker.check as worker
        inspect = worker.inspect_package

        def controlled_inspection(path):
            win.write(root / 'checking.json', {'pid': os.getpid()})
            # Fault barrier only in this experiment, after actual worker.main entered.
            win.until(lambda: (root / 'continue.json').exists(), 20)
            return inspect(path)

        worker.inspect_package = controlled_inspection
        sys.argv = ['apps.worker.check', str(root)]
        code = worker.main()
        win.write(root / 'worker_exit.json', {'code': code})
        return code
    except Exception as error:
        win.write(root / 'bootstrap_error.json', {'type': type(error).__name__, 'message': str(error)})
        return 3


def spawn_bound(root, job, binding, mode):
    env = {key: value for key, value in os.environ.items() if key.upper() in
           ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP')}
    # CPython's launcher contract restores venv paths without spawning its redirector.
    if mode != 'missing_venv':
        env['__PYVENV_LAUNCHER__'] = binding['venv_python']
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    block = c.create_unicode_buffer('\0'.join(f'{key}={value}' for key, value in
                                  sorted(env.items(), key=lambda pair: pair[0].upper())) + '\0\0')
    size = win.SIZE()
    win.init_attrs(None, 1, 0, c.byref(size))
    attrs = c.create_string_buffer(size.value)
    win.checked(win.init_attrs(attrs, 1, 0, c.byref(size)))
    try:
        jobs = (win.HANDLE * 1)(job)
        win.checked(win.update_attrs(attrs, 0, 0x2000D, jobs, c.sizeof(jobs), None, None))
        startup = win.StartupEx()
        startup.startup.cb = c.sizeof(startup)
        startup.attributes = c.cast(attrs, c.c_void_p)
        process = win.Process()
        exe = binding['base_python']['path']
        command = c.create_unicode_buffer(subprocess.list2cmdline(
            [exe, '-I', str(Path(__file__).resolve()), '--mode', 'worker', '--root', str(root)]))
        win.checked(win.create_process(exe, command, None, None, False,
                    0x80000 | 0x4 | 0x08000000 | 0x400, block, str(REPO),
                    c.byref(startup), c.byref(process)))
        return process
    finally:
        win.delete_attrs(attrs)


def supervise(root, mode):
    binding = json.loads((root / 'binding.json').read_text(encoding='utf-8'))
    job = win.checked(win.create_job(None, None))
    process = None
    try:
        limits = win.Limits()
        limits.basic.flags = 0x2000 | 0x8
        limits.basic.active_limit = 1
        win.checked(win.set_job(job, 9, c.byref(limits), c.sizeof(limits)))
        process = spawn_bound(root, job, binding, mode)
        win.write(root / 'process.json', {'supervisor_pid': os.getpid(),
                  'child': win.identity(process.process, process.pid)})
        # Harness holds an observation handle before any short-lived worker can exit.
        win.until(lambda: (root / 'observed.json').exists())
        if mode == 'kill_registered':
            win.write(root / 'checkpoint.json', {'phase': 'registered_suspended'})
            time.sleep(30)
        assert win.resume(process.thread) != 0xFFFFFFFF
        win.until(lambda: (root / 'checking.json').exists() or win.wait(process.process, 0) == 0)
        if mode == 'kill_check':
            assert (root / 'checking.json').exists()
            win.write(root / 'checkpoint.json', {'phase': 'inside_actual_worker'})
            time.sleep(30)
        win.write(root / 'continue.json', {})
        assert win.wait(process.process, 15000) == 0
        code = win.w.DWORD()
        win.checked(win.get_exit(process.process, c.byref(code)))
        win.write(root / 'supervisor_result.json', {'exit_code': code.value})
    finally:
        win.close(job)
        if process:
            assert win.wait(process.process, 5000) == 0
            win.close(process.thread)
            win.close(process.process)


def harness(root):
    sys.path.insert(0, str(REPO))
    from packages.infrastructure.runner import LocalRunner
    from packages.data.imports import canonical, sha
    from scripts.build_sample import build
    root.mkdir(parents=True, exist_ok=False)
    binding = {'venv': sys.prefix, 'venv_python': sys.executable,
               'fingerprint': LocalRunner(None).fingerprint()}
    for key, path in {'base_python': sys._base_executable,
                      'venv_config': Path(sys.prefix) / 'pyvenv.cfg', 'lock': REPO / 'uv.lock',
                      'bootstrap': Path(__file__), 'ownership_probe': Path(win.__file__)}.items():
        binding[key] = {'path': str(Path(path).resolve()), 'sha256': digest(path)}
    cases = []
    for mode in ('normal', 'kill_registered', 'kill_check', 'missing_venv', 'fingerprint_changed', 'invalid_input', 'poisoned_parent'):
        case = root / mode
        case.mkdir()
        build(case / 'input', spatial=True)
        context = {'job_id': 'job-' + uuid.uuid4().hex, 'attempt_id': 'attempt-' + uuid.uuid4().hex,
                   'spec_sha256': sha(canonical({'executor': 'synthetic_check/0.1'})),
                   'dataset_sha256': digest(case / 'input' / 'package.json')}
        (case / 'context.json').write_bytes(canonical(context))
        changed = json.loads(json.dumps(binding))
        if mode == 'fingerprint_changed':
            changed['fingerprint']['implementation_sha256'] = '0' * 64
        if mode == 'invalid_input':
            (case / 'input' / 'package.json').write_text('{}', encoding='utf-8')
        win.write(case / 'binding.json', changed)
        env = os.environ.copy()
        if mode == 'poisoned_parent':
            poison = case / 'poison'
            poison.mkdir()
            (poison / 'jsonschema.py').write_text('raise RuntimeError("poison imported")', encoding='utf-8')
            env.update(PYTHONPATH=str(poison), COSPACE_DATABASE_URL='must-not-reach-worker')
        with (case / 'supervisor.log').open('w', encoding='utf-8') as log:
            parent = subprocess.Popen([sys._base_executable, '-I', str(Path(__file__).resolve()),
                      '--mode', 'supervisor', '--case', mode, '--root', str(case)],
                      env=env, stdout=log, stderr=subprocess.STDOUT)
            handle = None
            try:
                win.until(lambda: (case / 'process.json').exists() or parent.poll() is not None)
                assert parent.poll() is None, 'supervisor failed; see log'
                record = json.loads((case / 'process.json').read_text())
                assert parent.pid == record['supervisor_pid']
                handle = win.checked(win.open_process(0x100000 | 0x1000, False, record['child']['pid']))
                assert win.identity(handle, record['child']['pid']) == record['child']
                win.write(case / 'observed.json', {})
                if mode.startswith('kill_'):
                    win.until(lambda: (case / 'checkpoint.json').exists())
                    parent.kill()
                status = parent.wait(timeout=25)
                assert win.wait(handle, 5000) == 0
                if not mode.startswith('kill_'):
                    assert status == 0
                report = case / 'validation_report.json'
                if mode in ('normal', 'poisoned_parent'):
                    result = json.loads(report.read_text(encoding='utf-8'))
                    assert all(result[key] == value for key, value in context.items())
                    assert result['validation']['passed'] is True
                    assert result['candidate_created'] is False and result['truth_created'] is False
                    observed = json.loads((case / 'environment.json').read_text())
                    assert observed['fingerprint'] == binding['fingerprint']
                    assert not observed['pythonpath_present'] and not observed['db_url_present']
                    assert observed['pid'] == record['child']['pid']
                else:
                    assert not report.exists(), 'failure exposed a successful report'
                if mode in ('missing_venv', 'fingerprint_changed'):
                    assert (case / 'bootstrap_error.json').exists()
                    assert json.loads((case / 'supervisor_result.json').read_text())['exit_code'] == 3
                if mode == 'invalid_input':
                    assert json.loads((case / 'worker_exit.json').read_text())['code'] == 2
                cases.append({'case': mode, 'passed': True, 'worker_exited': True,
                              'report_created': report.exists(), 'process': record})
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=12)
                if handle:
                    assert win.wait(handle, 5000) == 0
                    win.close(handle)
    win.write(root / 'results.json', {'scope': 'I4a actual fixed worker, no database recovery',
              'binding': binding, 'cases': cases})
    print(f'{len(cases)} actual-worker environment cases passed; evidence: {root}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('harness', 'supervisor', 'worker'), default='harness')
    parser.add_argument('--case', default='normal')
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'worker':
        raise SystemExit(bootstrap(args.root))
    elif args.mode == 'supervisor':
        supervise(args.root, args.case)
    else:
        harness(args.root.resolve())
