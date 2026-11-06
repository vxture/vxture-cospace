"""One fixed Python child, bounded output pipe and wall time. No OS sandbox claim."""
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
from importlib.metadata import version
from packages.data.imports import canonical, sha, now
from packages.infrastructure.files import bounded_read, safe_path, relative
from packages.infrastructure.jobs import JobError
from packages.service.sample import read_json


REPO = Path(__file__).resolve().parents[2]


class LocalRunner:
    def __init__(self, files):
        self.files = files

    def fingerprint(self):
        paths = sorted([*REPO.glob('packages/**/*.py'), *REPO.glob('apps/worker/*.py'),
                        *REPO.glob('contracts/schemas/*.json'), REPO / 'uv.lock'])
        return {'python': platform.python_version(), 'platform': platform.system(),
                'dependencies': {name: version(name) for name in ('jsonschema', 'sqlalchemy', 'psycopg', 'alembic')},
                'implementation_sha256': sha(canonical({p.relative_to(REPO).as_posix(): sha(p.read_bytes()) for p in paths}))}

    def execute(self, job, attempt, spec, manifest):
        work = safe_path(self.files.root / 'jobs' / job / attempt)
        work.mkdir(parents=True, exist_ok=False)
        source = self.files.root / 'datasets' / manifest['dataset_id']
        for member in manifest['members']:
            raw = bounded_read(source / relative(member['path']))
            if sha(raw) != member['sha256'] or len(raw) != member['bytes']:
                raise JobError('input_mismatch', 'input changed while copying attempt')
            target = work / 'input' / relative(member['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        context = {'job_id': job, 'attempt_id': attempt, 'spec_sha256': sha(canonical(spec)),
                   'dataset_sha256': spec['dataset_sha256']}
        (work / 'context.json').write_bytes(canonical(context))
        env = {key: value for key, value in os.environ.items() if key.upper() in
               ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'VIRTUAL_ENV')}
        env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.Popen([sys.executable, '-m', 'apps.worker.check', str(work)], cwd=REPO,
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        overflow = threading.Event()
        log = bytearray()
        limit = spec['config']['log_limit_bytes']
        def drain():
            while chunk := process.stdout.read(4096):
                remaining = limit - len(log)
                log.extend(chunk[:max(0, remaining)])
                if len(chunk) > remaining:
                    overflow.set()
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        start = time.monotonic()
        failure = None
        try:
            while process.poll() is None:
                if overflow.is_set():
                    failure = 'log_limit'; break
                if time.monotonic() - start >= spec['config']['timeout_seconds']:
                    failure = 'timeout'; break
                time.sleep(.02)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join(timeout=5)
            process.stdout.close()
            (work / 'worker.log').write_bytes(bytes(log))
        if failure or overflow.is_set() or process.returncode != 0:
            code = failure or ('log_limit' if overflow.is_set() else 'executor_failed')
            (work / 'execution.json').write_bytes(canonical({'code': code, 'exit_code': process.returncode,
                'log_truncated': overflow.is_set(), 'finished_at': now()}))
            raise JobError(code, 'fixed child failed; attempt diagnostic retained')
        raw = bounded_read(work / 'validation_report.json')
        report = read_json(raw)
        if (not isinstance(report, dict) or any(report.get(key) != value for key, value in context.items())
                or report.get('candidate_created') is not False or report.get('truth_created') is not False
                or not isinstance(report.get('validation'), dict) or report['validation'].get('passed') is not True
                or report['validation'].get('scene_id') != spec['scene_id']
                or report.get('data_kind') != 'synthetic'):
            raise JobError('invalid_output', 'child report does not bind fixed context')
        artifact = {'artifact_id': 'artifact-' + attempt.removeprefix('attempt-'), 'job_id': job,
                    'attempt_id': attempt, 'spec_sha256': context['spec_sha256'], 'sealed_at': now(),
                    'files': [{'path': name, 'sha256': sha(bounded_read(work / name)), 'bytes': (work / name).stat().st_size}
                              for name in ('validation_report.json', 'context.json', 'worker.log')]}
        (work / 'artifact.json').write_bytes(canonical(artifact))
        destination = safe_path(self.files.root / 'artifacts' / artifact['artifact_id'])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise JobError('immutable_conflict', 'artifact already exists')
        work.rename(destination)
        return artifact

    def report(self, artifact):
        root = safe_path(self.files.root / 'artifacts' / artifact['artifact_id'])
        if bounded_read(root / 'artifact.json') != canonical(artifact):
            raise JobError('content_corrupt', 'artifact manifest changed')
        for member in artifact['files']:
            raw = bounded_read(root / relative(member['path']))
            if sha(raw) != member['sha256'] or len(raw) != member['bytes']:
                raise JobError('content_corrupt', 'artifact member changed')
        return read_json(bounded_read(root / 'validation_report.json'))
