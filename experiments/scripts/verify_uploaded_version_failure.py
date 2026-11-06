"""Fail a real derived-view worker in an exclusive copy of the P11 runtime.

No failure marker or broken artifact is written into the running demo. Source
paths in copied input records remain read-only; only the exclusive copy builds.
"""
import argparse
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler

from experiments.scripts.verify_preview_workflow import inventory


def verify(args):
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists() or source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError('exclusive_output_outside_source_required')
    before = inventory(source)
    output.mkdir(parents=True)
    runtime = output / 'runtime'
    runtime.mkdir()
    for path in source.glob('preview-*'):
        if path.is_dir():
            # Input records already bind immutable absolute source paths. The
            # failure server only reads those paths; copying uploaded raw images
            # adds no isolation and can exceed Windows path length limits.
            ignore = shutil.ignore_patterns('uploads', '.upload-staging') if path.name == 'preview-inputs' else None
            shutil.copytree(path, runtime / path.name, ignore=ignore)
    save(output / 'source-before.json', before)
    save(output / 'seed.json', {'scenes': [args.space, 'space-0004d0e3c133f5fb']})
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
    csrf = ''
    trace = []
    checks = []

    def check(ok, name):
        if not ok:
            raise AssertionError(name)
        checks.append(name)

    def http(path, body=None, status=200):
        headers = {'Content-Type': 'application/json', 'Origin': origin, 'X-CoSpace-CSRF': csrf} if body is not None else {}
        url = path if path.startswith('http') else origin + path
        try:
            with client.open(Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers), timeout=50) as response:
                code, raw = response.status, response.read()
        except HTTPError as exc:
            code, raw = exc.code, exc.read()
        trace.append({'path': path.split('?')[0], 'status': code, 'method': 'POST' if body is not None else 'GET'})
        assert code == status, (path, code, raw[:300])
        return json.loads(raw)

    with (output / 'server.log').open('wb') as log:
        process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m',
            'experiments.scripts.verify_release_consumption', '--serve', '--output', str(output), '--port', str(port)],
            stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            for _ in range(180):
                if process.poll() is not None:
                    raise RuntimeError('exclusive_server_exited')
                try:
                    http('/api/auth/config')
                    break
                except URLError:
                    time.sleep(.1)
            else:
                raise TimeoutError('exclusive_server_start_timeout')
            with client.open(origin + '/auth/login', timeout=20) as response:
                html, url = response.read().decode(), response.geturl()
            link = next(v for v in re.findall(r'href="([^"]+)"', html) if 'user=usr_manager' in v)
            with client.open(urljoin(url, link), timeout=20) as response:
                response.read()
            session = http('/api/auth/session')
            assert session['user']['subject'] == 'usr_manager'
            csrf = session['csrf']
            selection = http('/api/selection?space_id=' + args.space)
            pubs = http('/api/publications?space_id=' + args.space)
            infos = {p['id']: http('/publications/' + p['id'] + '/offline.json') for p in pubs['publications']}
            check(len(infos) == 2, 'exclusive_copy_contains_both_fixed_versions')
            (output / 'fail-next-human').write_text('P11 one-shot child exit 23', encoding='utf-8')
            job = http('/api/builds', {'space_id': args.space, 'input_id': args.input,
                'batch_id': args.batch, 'batch_revision': 2}, 202)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                job = next(j for j in http('/api/builds?space_id=' + args.space)['jobs'] if j['id'] == job['id'])
                if job['state'] not in ('queued', 'running'):
                    break
                time.sleep(.25)
            else:
                raise TimeoutError('exclusive_worker_timeout')
            check(job['state'] == 'views_failed' and bool(job.get('frozen_model')), 'real_model_freezes_but_derived_view_worker_fails')
            tasks = [json.loads(p.read_bytes()) for p in (runtime / 'preview-builds').rglob('task.json')]
            failed = [t for t in tasks if t.get('job_id') == job['id'] and t.get('view_kind') == 'human' and t.get('state') == 'failed']
            # Task storage names are versioned; discover task files by profile.
            if not failed:
                tasks = [json.loads(p.read_bytes()) for p in (runtime / 'preview-builds').rglob('*.json')]
                failed = [t for t in tasks if isinstance(t, dict) and t.get('profile') == 'cospace.view-task/0.1'
                          and t.get('job_id') == job['id'] and t.get('view_kind') == 'human' and t.get('state') == 'failed']
            check(bool(failed) and not (output / 'fail-next-human').exists(), 'one_shot_failure_is_recorded_in_real_view_task')
            check(http('/api/selection?space_id=' + args.space) == selection, 'failed_update_keeps_existing_candidate_selection')
            check(http('/api/publications?space_id=' + args.space) == pubs, 'failed_update_does_not_create_or_rewrite_fixed_publications')
            http('/api/candidate-comparisons', {'space_id': args.space, 'candidate_id': job['id'], 'expected_revision': selection['revision']}, 409)
            check(True, 'failed_candidate_cannot_be_reviewed_or_selected')
            for identity, info in infos.items():
                model = http('/publications/' + identity + '/api/preview')
                point = http('/publications/' + identity + '/api/query', {'point_m': [10000, 10000, 10000]})
                check(model['space_id'] == args.space and point['state'] == 'unknown'
                      and http('/publications/' + identity + '/offline.json')['sha256'] == info['sha256'],
                      'fixed_' + identity + '_still_reads_queries_and_exports_same_digest')
            check(inventory(source) == before, 'running_demo_and_all_source_files_unchanged_by_failure_test')
            report = {'status': 'passed', 'passed': len(checks), 'checks': checks, 'job': job,
                      'failed_view_tasks': failed, 'http_trace': trace, 'source_unchanged': True,
                      'identity_provider': 'local_mock_only', 'quality': 'unverified', 'robot_ready': False}
            save(output / 'acceptance.json', report)
            print(json.dumps({'status': 'passed', 'passed': len(checks), 'failed_job': job['id']}))
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--space', required=True)
    p.add_argument('--input', required=True)
    p.add_argument('--batch', required=True)
    verify(p.parse_args())
