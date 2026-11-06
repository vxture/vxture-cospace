"""H3c: combine lifecycle gates, restart, evidence gaps and offline recovery in a new copy.

Requires an idle H1 acceptance runtime and its original frozen source files. Writes only
the exclusive output; original/source inventories include an independent control DB check.
"""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener

from jsonschema import Draft202012Validator, FormatChecker
from experiments.scripts.verify_preview_workflow import inventory
from packages.views.agent.preview_offline import sha

PROFILE = 'cospace.preview-lifecycle-acceptance/0.1'


def tree(root):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def run(args):
    source, output = args.source.resolve(), args.output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('source_and_output_must_be_separate')
    if output.is_relative_to(Path('var/nyu').resolve()):
        raise ValueError('original_runtime_is_read_only')
    seed = json.loads((source / 'acceptance.json').read_bytes())
    if seed.get('profile') != 'cospace.preview-batch-acceptance/0.1':
        raise ValueError('idle_H1_acceptance_runtime_required')
    if (source / 'runtime/preview-lifecycle.sqlite3').exists():
        raise ValueError('clean_H1_lifecycle_seed_required')
    if {s['sample'] for s in seed['samples']} != {'nyu', 'laser'}:
        raise ValueError('two_sample_seed_required')
    for p in (source / 'runtime/preview-builds').glob('*/job.json'):
        if json.loads(p.read_bytes()).get('state') in ('running', 'queued'):
            raise ValueError('source_runtime_must_be_idle')
    original = inventory(Path('var/nyu'))
    original_control = Path('var/nyu/preview-lifecycle.sqlite3')
    original_control_digest = sha(original_control.read_bytes()) if original_control.exists() else None
    source_before = tree(source / 'runtime')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source / 'runtime', output / 'runtime')
    (output / 'original-before.json').write_text(json.dumps(original, indent=2) + '\n', encoding='utf-8')
    (output / 'source-before.json').write_text(json.dumps(source_before, indent=2) + '\n', encoding='utf-8')
    immutable = {k: v for k, v in source_before.items() if k != 'preview-inputs/acquisition-batches.sqlite3'
                 and not k.startswith('.')}
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    # This harness talks only to its loopback child, independently of OS proxy settings.
    opener = build_opener(ProxyHandler({}))
    checks, trace, samples, contexts, processes = [], [], [], [], []
    server = log = None
    validators = {name: Draft202012Validator(json.loads(Path(path).read_bytes()), format_checker=FormatChecker())
                  for name, path in {'control': 'contracts/schemas/preview-artifact-control-v0.1.schema.json',
                                     'catalog': 'contracts/schemas/preview-artifacts-v0.1.schema.json'}.items()}

    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def check(value, name):
        if not value:
            raise AssertionError(name)
        checks.append(name)

    def http(path, body=None, expected=200, binary=False):
        request = Request(origin + path, data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            with opener.open(request, timeout=45) as response:
                status, raw, cache = response.status, response.read(), response.headers.get('Cache-Control')
        except HTTPError as exc:
            status, raw, cache = exc.code, exc.read(), exc.headers.get('Cache-Control')
        trace.append({'method': request.get_method(), 'path': path, 'status': status,
                      'expected_status': expected, 'cache_control': cache})
        if status != expected:
            raise AssertionError((path, status, raw[:500]))
        if path.startswith('/publications/') and cache != 'no-store':
            raise AssertionError(('distribution_cache_policy', path, cache))
        return raw if binary else json.loads(raw)

    def stop():
        nonlocal server, log
        if server:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill(); server.wait(timeout=10)
            server = None
        if log:
            log.close(); log = None

    def start():
        nonlocal server, log
        log = (output / f'server-{len(processes) + 1}.log').open('wb')
        server = subprocess.Popen([sys.executable, '-X', 'utf8', '-m',
                                   'experiments.scripts.verify_preview_workflow', '--serve', '--output', str(output),
                                   '--port', str(port)], stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        processes.append(server.pid)
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError('isolated_server_exited')
            try:
                http('/api/projects'); return
            except URLError:
                time.sleep(.1)
        raise RuntimeError('isolated_server_start_timeout')

    def report(space, key):
        value = http('/api/artifact-control?space_id=' + space + '&artifact=' + key)
        validators['control'].validate(value)
        return value

    def body(current, op):
        return {'space_id': current['space_id'], 'artifact': current['artifact'],
                'expected_revision': current['record']['revision'],
                'expected_snapshot_sha256': current['snapshot_sha256'],
                'operation': op, 'reason': 'H3c完整生命周期隔离验收：' + op}

    def change(space, key, op):
        return http('/api/artifact-control/transitions', body(report(space, key), op))

    def batch_change(context, op):
        current = http('/api/batches/' + context['batch_id'] + '?space_id=' + context['space_id'])['batch']
        return http('/api/batches/' + current['id'] + '/transitions',
                    {'space_id': context['space_id'], 'expected_revision': current['revision'],
                     'operation': op, 'reason': 'H3c完整生命周期隔离验收：' + op})

    def checkpoint(context, stage):
        space = context['space_id']
        value = {'stage': stage, 'sample': context['sample'], 'space_id': space,
                 'batch': http('/api/batches/' + context['batch_id'] + '?space_id=' + space)['batch'],
                 'controls': {name: report(space, context[name]) for name in ('input_key', 'candidate_key', 'publication_key')},
                 'workflow': http('/api/workflow?space_id=' + space),
                 'catalog': http('/api/artifacts?space_id=' + space),
                 'selection': http('/api/selection?space_id=' + space)}
        validators['catalog'].validate(value['catalog'])
        save(context['sample'] + '-' + stage + '.json', value)
        return value

    def assert_selection(context):
        check(http('/api/selection?space_id=' + context['space_id']) == context['selection'],
              context['sample'] + ': selection_unchanged_' + str(len(checks)))

    def offline_child(context, mode):
        folder = output / context['sample']; folder.mkdir(exist_ok=True)
        bundle = folder / 'held.zip'
        if mode == 'install':
            bundle.write_bytes(context['bundle'])
        elif bundle.exists():
            bundle.unlink()  # Store must restore without the originally downloaded file.
        target = folder / (mode + '-result.json')
        request = {'consumer': str(folder / 'consumer'), 'space': context['space_id'],
                   'publication': context['publication_id'], 'sha256': sha(context['bundle']),
                   'mode': mode, 'bundle': str(bundle), 'point': context['point'],
                   'bounds': context['bounds'], 'frame_id': context['manifest']['frame_id'], 'result': str(target)}
        request_path = folder / (mode + '-request.json'); save(request_path.relative_to(output), request)
        subprocess.run([sys.executable, '-X', 'utf8', '-m', 'experiments.scripts.verify_preview_workflow',
                        '--consumer-request', str(request_path)], check=True, capture_output=True, timeout=30)
        result = json.loads(target.read_bytes())
        check(result['network_disabled'] and result['results'] == context['online'],
              context['sample'] + ': offline_' + mode + '_matches_original_online')
        return result

    try:
        start()
        for sample in seed['samples']:
            c = {**sample, 'input_key': 'input:' + sample['input_id'],
                 'candidate_key': 'candidate:' + sample['geometry_candidate'],
                 'publication_key': 'publication:' + sample['publication_id']}
            contexts.append(c)
            label, space = c['sample'], c['space_id']; prefix = '/publications/' + c['publication_id'] + '/'
            print(label + ': baseline → batch/input disabled → ancestor archived → publication paused', flush=True)
            c['prefix'] = prefix; c['selection'] = http('/api/selection?space_id=' + space)
            c['manifest'] = http(prefix + 'model.json'); c['objects'] = http(prefix + 'api/objects')
            c['point'] = c['objects']['objects'][0]['anchor_m']; r = c['manifest']['agent_view']['resolution_m']
            c['bounds'] = [[v - r for v in c['point']], [v + r for v in c['point']]]
            c['bundle'] = http(prefix + 'offline.zip', binary=True)
            c['online'] = {'objects': c['objects'], 'point': http(prefix + 'api/query', {'point_m': c['point']}),
                           'range': http(prefix + 'api/query-range', {'bounds_m': c['bounds'],
                                                                    'frame_id': c['manifest']['frame_id'], 'limit': 1024})}
            initial = checkpoint(c, 'baseline')
            check(all(v['record']['revision'] == 0 and v['record']['lifecycle_state'] == 'active'
                      for v in initial['controls'].values()), label + ': clean_control_baseline')
            check(initial['batch']['state'] == 'sealed', label + ': sealed_batch_baseline')
            check(initial['workflow']['publication_ref']['publication_id'] == c['publication_id'], label + ': matching_fixed_release')
            stale = body(initial['controls']['input_key'], 'disable_input')
            disabled_batch = batch_change(c, 'disable')
            check(disabled_batch['state'] == 'disabled', label + ': batch_disabled_independently')
            http('/api/artifact-control/transitions', stale, 409)
            check(report(space, c['input_key'])['record']['revision'] == 0, label + ': batch_change_invalidates_old_report_without_commit')
            for params in ({}, {'batch_id': c['batch_id'], 'batch_revision': c['batch_revision']},
                           {'batch_id': c['batch_id'], 'batch_revision': disabled_batch['revision']}):
                http('/api/builds', {'space_id': space, 'input_id': c['input_id'], **params}, 409)
            check(True, label + ': disabled_batch_has_no_direct_or_stale_revision_bypass')
            change(space, c['input_key'], 'disable_input')
            input_report = report(space, c['input_key'])
            action = next(a for a in input_report['actions'] if a['operation'] == 'archive_input')
            check(not action['allowed'] and 'current_selection_depends_on_input' in action['blockers'], label + ': selected_source_archive_blocked')
            http('/api/artifact-control/transitions', body(input_report, 'archive_input'), 409)
            http('/api/artifact-control/transitions', body(report(space, 'candidate:' + c['candidate_id']), 'archive_candidate'), 409)
            change(space, c['candidate_key'], 'archive_candidate')
            http('/api/selection', {'space_id': space, 'candidate_id': c['geometry_candidate'],
                                    'expected_revision': c['selection']['revision']}, 409)
            http('/api/publications', {'space_id': space, 'candidate_id': c['geometry_candidate'],
                                       'expected_revision': c['selection']['revision']}, 409)
            rule = http('/api/ontologies')['ontologies'][0]
            catalog = http('/api/artifacts?space_id=' + space)
            model_hash = next(i for i in catalog['items'] if i['key'] == c['candidate_key'])['model_manifest_sha256']
            http('/api/semantic-candidates', {'space_id': space, 'base_candidate_id': c['geometry_candidate'],
                 'base_manifest_sha256': model_hash, 'ontology_ref': {k: rule[k] for k in ('ontology_id', 'version', 'sha256')},
                 'objects': [{'object_id': 'h3c-example', 'type_id': 'room', 'properties': {'name': '待核实'}, 'point_index': 0}]}, 409)
            check(True, label + ': archived_ancestor_blocks_new_select_derive_publish')
            check(http(prefix + 'offline.zip', binary=True) == c['bundle'] and http(prefix + 'api/objects') == c['objects'],
                  label + ': upstream_controls_do_not_cascade_to_existing_release')
            c['consumer_install'] = offline_child(c, 'install')
            change(space, c['publication_key'], 'pause_distribution')
            for path in ('', 'human.ply', 'agent.npz', 'offline.zip', 'api/objects'):
                result = http(prefix + path, expected=409)
                check(result['detail'] == 'publication_distribution_paused', label + ': combined_state_denies_' + (path or 'HTML'))
            http(prefix + 'api/query', {'point_m': c['point']}, 409)
            http(prefix + 'api/query-range', {'bounds_m': c['bounds'], 'frame_id': c['manifest']['frame_id'], 'limit': 1024}, 409)
            blocked = checkpoint(c, 'combined-blocked')
            check(blocked['workflow']['next_stage'] == 'delivery'
                  and all(s['status'] == 'blocked' for s in blocked['workflow']['stages'] if s['id'] in ('space', 'delivery')),
                  label + ': blocked_workflow_points_to_distribution_management')
            check(http('/api/spaces/' + space)['publication_id'] is None, label + ': paused_default_not_replaced_by_history')
            c['blocked_records'] = {k: v['record'] for k, v in blocked['controls'].items()}
            c['blocked_batch'] = blocked['batch']; assert_selection(c)
        stop(); start()
        check(len(set(processes)) == 2, 'service_restarted_with_new_process')
        for c in contexts:
            label, space, prefix = c['sample'], c['space_id'], c['prefix']
            print(label + ': restart → missing evidence → restore layers → real build → offline restore', flush=True)
            restarted = checkpoint(c, 'after-restart')
            check({k: v['record'] for k, v in restarted['controls'].items()} == c['blocked_records']
                  and restarted['batch'] == c['blocked_batch'], label + ': combined_states_and_history_persist_across_restart')
            http('/api/builds', {'space_id': space, 'input_id': c['input_id'], 'batch_id': c['batch_id'],
                                 'batch_revision': c['blocked_batch']['revision']}, 409)
            http(prefix + 'offline.zip', expected=409)
            c['consumer_restore'] = offline_child(c, 'restore')
            check(c['consumer_install']['pid'] != c['consumer_restore']['pid'],
                  label + ': offline_restart_works_while_all_four_layers_inactive')
            # Only the isolated registry is fault-injected. Source sensor files are never changed.
            path = output / 'runtime/preview-inputs' / (c['input_id'] + '.json'); raw = path.read_bytes()
            clean_restore = body(report(space, c['publication_key']), 'restore')
            try:
                path.unlink()
                missing = report(space, c['publication_key']); save(label + '-missing-evidence.json', missing)
                check(missing['impact']['issues'] and all(not a['allowed'] for a in missing['actions']),
                      label + ': missing_registry_is_unknown_not_zero_references')
                http('/api/artifact-control/transitions', clean_restore, 409)
                http('/api/artifact-control/transitions', body(missing, 'restore'), 409)
                check(report(space, c['publication_key'])['record'] == c['blocked_records']['publication_key'],
                      label + ': missing_evidence_cannot_restore_or_append_history')
                http(prefix + 'model.json', expected=409)
            finally:
                path.write_bytes(raw)
            foreign = seed['foreign_space_id']
            http('/api/artifact-control?space_id=' + foreign + '&artifact=' + c['publication_key'], expected=404)
            http('/api/artifact-control/transitions', {**clean_restore, 'space_id': foreign}, 404)
            check(True, label + ': foreign_space_cannot_read_or_restore')
            restored_pub = change(space, c['publication_key'], 'restore')
            check(restored_pub['lifecycle_state'] == 'active' and restored_pub['revision'] == 2, label + ': restore_same_publication')
            restored = checkpoint(c, 'publication-restored')
            check(restored['batch']['state'] == 'disabled'
                  and restored['controls']['input_key']['record']['lifecycle_state'] == 'disabled'
                  and restored['controls']['candidate_key']['record']['lifecycle_state'] == 'archived',
                  label + ': publication_restore_does_not_enable_upstream')
            check(http(prefix + 'offline.zip', binary=True) == c['bundle'] and http(prefix + 'api/objects') == c['objects'],
                  label + ': same_fixed_bytes_restored_with_upstream_still_inactive')
            check(http('/api/spaces/' + space)['publication_id'] == c['publication_id'], label + ': default_entry_restored_explicitly')
            change(space, c['candidate_key'], 'restore')
            check(report(space, c['input_key'])['record']['lifecycle_state'] == 'disabled', label + ': candidate_restore_does_not_enable_source')
            change(space, c['input_key'], 'restore')
            batch_now = http('/api/batches/' + c['batch_id'] + '?space_id=' + space)['batch']
            http('/api/builds', {'space_id': space, 'input_id': c['input_id'], 'batch_id': c['batch_id'],
                                 'batch_revision': batch_now['revision']}, 409)
            check(True, label + ': restored_input_still_requires_batch_restore')
            new_batch = batch_change(c, 'restore')
            http('/api/builds', {'space_id': space, 'input_id': c['input_id'], 'batch_id': c['batch_id'],
                                 'batch_revision': batch_now['revision']}, 409)
            check(True, label + ': restored_batch_rejects_old_revision')
            admitted = http('/api/builds', {'space_id': space, 'input_id': c['input_id'], 'batch_id': c['batch_id'],
                                           'batch_revision': new_batch['revision']}, 202)
            deadline = time.monotonic() + 120
            while True:
                job = next(j for j in http('/api/builds?space_id=' + space)['jobs'] if j['id'] == admitted['id'])
                if job['state'] not in ('queued', 'running') or time.monotonic() >= deadline:
                    break
                time.sleep(.25)
            check(job['state'] == 'succeeded', label + ': all_layers_restored_real_build_succeeds')
            check(job['batch_ref']['admitted_revision'] == new_batch['revision'], label + ': new_build_captures_new_batch_revision')
            check(http(prefix + 'model.json')['source']['batch_ref'] == c['batch_ref'], label + ': old_release_keeps_original_batch_revision')
            assert_selection(c)
            final = checkpoint(c, 'restored')
            check(all(v['record']['lifecycle_state'] == 'active' and v['record']['revision'] == 2
                      and len(v['record']['history']) == 2 for v in final['controls'].values()), label + ': exact_two_event_histories')
            check(final['workflow']['stages'][-1]['status'] == 'unobserved'
                  and not final['workflow']['consumer_state_checked'], label + ': server_does_not_claim_offline_activation')
            samples.append({**{k: v for k, v in c.items() if k in sample_fields()}, 'new_build_id': admitted['id'],
                            'final_batch_revision': new_batch['revision'], 'final_control_revisions': {'input': 2, 'candidate': 2, 'publication': 2},
                            'package_sha256': sha(c['bundle']), 'consumer_pids': [c['consumer_install']['pid'], c['consumer_restore']['pid']]})
        stop(); start()
        check(len(set(processes)) == 3, 'restored_runtime_restarted_again')
        for c in contexts:
            value = checkpoint(c, 'final-restart')
            check(all(v['record']['lifecycle_state'] == 'active' and v['record']['revision'] == 2
                      for v in value['controls'].values()) and value['batch']['state'] == 'sealed', c['sample'] + ': final_states_survive_second_restart')
            check(http(c['prefix'] + 'offline.zip', binary=True) == c['bundle'], c['sample'] + ': fixed_package_unchanged_after_second_restart')
            assert_selection(c)
        stop()
        current = tree(output / 'runtime')
        check(all(current.get(k) == v for k, v in immutable.items()), 'all_preexisting_immutable_runtime_files_unchanged')
        check(tree(source / 'runtime') == source_before, 'source_runtime_all_files_unchanged_including_databases')
        check(inventory(Path('var/nyu')) == original, 'original_managed_files_unchanged')
        check((sha(original_control.read_bytes()) if original_control.exists() else None) == original_control_digest,
              'original_lifecycle_database_unchanged_or_absent')
        result = {'profile': PROFILE, 'status': 'passed', 'passed': len(checks), 'checks': checks,
                  'samples': samples, 'server_processes': processes, 'server_restarts': 2,
                  'original_managed_files_unchanged': len(original), 'source_all_files_unchanged': len(source_before),
                  'preexisting_immutable_files_unchanged': len(immutable), 'http_requests_checked': len(trace),
                  'transport': 'real_loopback_HTTP', 'consumer_network_disabled': True,
                  'identity': 'local_engineer_unverified_identity', 'quality': 'unverified',
                  'production_ready': False, 'robot_ready': False}
        save('acceptance.json', result); save('http-trace.json', trace)
        print(json.dumps({k: result[k] for k in ('profile', 'status', 'passed', 'http_requests_checked',
                                               'server_restarts', 'original_managed_files_unchanged')}, ensure_ascii=False), flush=True)
    except BaseException as exc:
        save('failure.json', {'profile': PROFILE, 'status': 'failed', 'error': repr(exc), 'completed_checks': checks})
        save('http-trace.json', trace)
        raise
    finally:
        stop()


def sample_fields():
    return ('sample', 'space_id', 'input_id', 'geometry_candidate', 'candidate_id', 'publication_id', 'batch_id')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
