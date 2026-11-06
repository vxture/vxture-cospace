"""Internal synthetic delivery workflow acceptance; real CLI and loopback HTTP, no robot grant."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler, Request

from apps.api.managed import create_managed_app
from packages.infrastructure.delivery_reports import ReportArchive
from packages.infrastructure.files import safe_path


class AcceptanceFailure(Exception):
    pass


STAGES = ('clean', 'pending', 'planned', 'reconciled_missing_grant')
REQUIRED_CHECKS = tuple(stage + '.' + suffix for stage in STAGES
                        for suffix in ('cli_exit', 'source_unchanged', 'diagnostic', 'no_authority')) + (
    'generation.distinct_batches', 'generation.no_temporary_files', 'http.list',
    *(stage + '.http_fixed_selection' for stage in STAGES),
    'http.old_report_stays_fixed', 'http.wrong_scene_list_empty', 'http.wrong_scene_selection_denied',
    'http.missing_selection_no_fallback', 'http.no_write_method', 'http.archive_unchanged',
    'http.corrupt_selection_denied', 'http.corrupt_list_no_partial_success')


def record(checks, identity, condition, **observed):
    checks.append({'id': identity, 'passed': bool(condition), 'observed': observed})
    if not condition:
        raise AcceptanceFailure(identity)


@contextmanager
def local_http(archive, workbench=None):
    """Reserve an ephemeral loopback socket without a free-port race; bounded shutdown."""
    import uvicorn
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    app = create_managed_app(None, delivery_archive=ReportArchive(archive), workbench_dir=workbench)
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise AcceptanceFailure('http_start_failed')
            time.sleep(.01)
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        if thread.ident is not None:
            thread.join(5)
        listener.close()
        if thread.is_alive():
            raise AcceptanceFailure('http_shutdown_failed')


def request(base, path, method='GET'):
    opener = build_opener(ProxyHandler({}))
    try:
        response = opener.open(Request(base + path, method=method), timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers.get('Cache-Control'), json.loads(response.read(2 * 1024 * 1024))


def source_snapshot(roots):
    return {f'{index}/{p.relative_to(root).as_posix()}': hashlib.sha256(p.read_bytes()).hexdigest()
            for index, root in enumerate(roots) for p in root.rglob('*') if p.is_file()}


def _exercise(output, checks):
    # Deliberately reuse the existing test-only factories. Requires dev pytest; no production seed input.
    from tests.test_recovery_session import consumer
    from tests.test_recovery_state import recovery, pending, plan
    from tests.test_validity_probe import gate, proofs
    with tempfile.TemporaryDirectory(prefix='cospace-delivery-acceptance-') as temporary:
        root = Path(temporary)
        fixture = consumer.__wrapped__(recovery.__wrapped__(gate.__wrapped__(root), root), root)
        binding = fixture['binding']
        binding_file = root / 'binding.json'
        binding_file.write_text(json.dumps(binding), encoding='utf-8')
        roots = [fixture['files'].root, fixture['journal'].root]
        receipts = {}
        def generate(stage, expected_exit, expected_codes):
            before = source_snapshot(roots)
            command = [sys.executable, '-m', 'experiments.scripts.delivery_generate', '--files', str(roots[0]),
                       '--journal', str(roots[1]), '--binding', str(binding_file), '--output', str(output / 'reports')]
            child = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=30)
            record(checks, stage + '.cli_exit', child.returncode == expected_exit, actual=child.returncode, expected=expected_exit)
            receipt = json.loads(child.stdout)
            record(checks, stage + '.source_unchanged', source_snapshot(roots) == before)
            selected = ReportArchive(output / 'reports').read(binding['scene_id'], binding['release_id'], receipt['report_key'])
            report = selected['report']
            codes = {item['code'] for item in report['findings']}
            record(checks, stage + '.diagnostic', codes == expected_codes, codes=sorted(codes))
            record(checks, stage + '.no_authority', report['authorized'] is False and report['robot_ready'] is False
                   and report['repair_authorized'] is False and report['validity'] == 'not_evaluated')
            receipts[stage] = receipt
        generate('clean', 0, set())
        pending(fixture, proofs(fixture, sequence=2)[0])
        generate('pending', 2, {'component_needs_attention'})
        _, proposed = plan(fixture)
        generate('planned', 2, {'component_needs_attention'})
        fixture['journal'].commit_recovery(proposed)
        generate('reconciled_missing_grant', 2, {'proof_fields_missing'})
        (output / 'receipts.json').write_text(json.dumps(receipts, indent=2), encoding='utf-8')
        record(checks, 'generation.distinct_batches', len({r['report_id'] for r in receipts.values()}) == 4)
        record(checks, 'generation.no_temporary_files', not list((output / 'reports').glob('.writing-*')))
        before_archive = source_snapshot([output / 'reports'])
        with local_http(output / 'reports') as base:
            path = f"/scenes/{binding['scene_id']}/releases/{binding['release_id']}/delivery-reports"
            status, cache, listing = request(base, path)
            record(checks, 'http.list', status == 200 and cache == 'no-store' and len(listing['items']) == 4
                   and listing['selection'] == 'explicit_key_required', count=len(listing.get('items', [])))
            for stage, receipt in receipts.items():
                status, cache, result = request(base, path + '/' + receipt['report_key'])
                record(checks, stage + '.http_fixed_selection', status == 200 and cache == 'no-store'
                       and result['source']['report_key'] == receipt['report_key']
                       and result['source']['sha256'] == receipt['sha256']
                       and result['report']['generation']['report_id'] == receipt['report_id'])
            status, _, old = request(base, path + '/' + receipts['clean']['report_key'])
            record(checks, 'http.old_report_stays_fixed', status == 200 and not old['report']['needs_attention'])
            wrong = path.replace(binding['scene_id'], 'different-scene')
            record(checks, 'http.wrong_scene_list_empty', request(base, wrong)[2]['items'] == [])
            record(checks, 'http.wrong_scene_selection_denied', request(base, wrong + '/' + receipts['clean']['report_key'])[0] == 409)
            missing = receipts['clean']['report_id'] + '.' + '0' * 64
            record(checks, 'http.missing_selection_no_fallback', request(base, path + '/' + missing)[0] == 503)
            record(checks, 'http.no_write_method', request(base, path, method='POST')[0] == 405)
        record(checks, 'http.archive_unchanged', source_snapshot([output / 'reports']) == before_archive)
        # Corrupt an isolated copy; retained main archive remains usable for browser review.
        fault_root = root / 'fault-reports'
        fault_root.mkdir()
        key = receipts['clean']['report_key']
        (fault_root / (key + '.json')).write_bytes((output / 'reports' / (key + '.json')).read_bytes() + b' ')
        with local_http(fault_root) as base:
            status, cache, error = request(base, path + '/' + key)
            record(checks, 'http.corrupt_selection_denied', status == 503 and cache == 'no-store' and 'report' not in error)
            record(checks, 'http.corrupt_list_no_partial_success', request(base, path)[0] == 503)


def run(output):
    output = safe_path(output)
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier run.
    checks = []
    started = time.monotonic()
    failure = None
    try:
        if os.name != 'nt':
            raise AcceptanceFailure('windows_required')
        _exercise(output, checks)
        identities = [item['id'] for item in checks]
        if len(identities) != len(REQUIRED_CHECKS) or set(identities) != set(REQUIRED_CHECKS):
            raise AcceptanceFailure('required_check_coverage_incomplete')
    except Exception as error:
        # Do not persist raw exception bodies, test key material or arbitrary command outputs.
        failure = {'type': type(error).__name__, 'check_id': str(error) if isinstance(error, AcceptanceFailure) else 'execution_failed'}
    result = {'schema_version': 'cospace.delivery-workflow-acceptance/0.1', 'test_only': True,
              'passed': failure is None and bool(checks) and all(c['passed'] for c in checks),
              'checks': checks, 'failure': failure, 'elapsed_seconds': round(time.monotonic() - started, 3),
              'required_checks': list(REQUIRED_CHECKS),
              'scope': 'synthetic CLI and real loopback HTTP; no release manager',
              'browser_executed': False, 'production_accepted': False,
              'authorized': False, 'robot_ready': False, 'repair_authorized': False}
    (output / 'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    sources = ['experiments/scripts/delivery_acceptance.py', 'experiments/scripts/delivery_generate.py',
               'packages/infrastructure/delivery_reports.py', 'apps/api/managed.py',
               'experiments/scripts/delivery_audit.py', 'packages/service/delivery.py',
               'packages/data/delivery_report.py', 'tests/test_recovery_session.py',
               'tests/test_recovery_state.py', 'tests/test_validity_probe.py', 'tests/test_trust_proof.py']
    environment = {'python': platform.python_version(), 'platform': platform.platform(),
                   'source_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources},
                   'artifact_sha256': {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in output.rglob('*') if p.is_file()}}
    (output / 'environment.json').write_text(json.dumps(environment, indent=2), encoding='utf-8')
    return result


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = run(args.output)
    except (OSError, ValueError):
        print(json.dumps({'error': 'new_writable_output_directory_required', 'authorized': False}))
        return 1
    print(json.dumps({'passed': result['passed'], 'checks': len(result['checks']), 'failure': result['failure'], 'authorized': False}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
