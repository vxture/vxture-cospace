"""P11: actual different-content releases, independent offline switch and rollback.

Only reads browser downloads and receipts. No builds, selection, publishing or
network access is performed by the independent consumer processes.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from experiments.scripts.verify_scene_journey_consumer import cli_result
from packages.views.agent.preview_offline import OfflinePreview, sha


def verify(args):
    report = cli_result(args.browser)
    output = args.output.resolve()
    original = Path('var/nyu').resolve()
    if output.is_relative_to(original) or original.is_relative_to(output):
        raise ValueError('exclusive_output_outside_original_required')
    output.mkdir(parents=True, exist_ok=False)
    checks, releases, processes = [], [], []

    def check(ok, name):
        if not ok:
            raise AssertionError(name)
        checks.append(name)

    for index, item in enumerate(report['results']):
        raw = Path(item['bundle']).read_bytes()
        check(sha(raw) == item['package_sha256'], f'v{index+1}_browser_download_digest_matches')
        offline = OfflinePreview(raw, item['publication_id'], item['package_sha256'])
        source = offline.manifest['source']
        check(source['input_binding']['id'] == item['input_id'] and source['batch_ref']['batch_id'] == item['batch_id']
              and source['batch_ref']['admitted_revision'] == 2, f'v{index+1}_exact_input_and_sealed_batch')
        bundle = output / f'v{index+1}-source.zip'
        shutil.copyfile(item['bundle'], bundle)
        releases.append({'id': item['publication_id'], 'sha256': item['package_sha256'], 'bundle': str(bundle),
            'point': item['point'], 'unknown': item['unknown'], 'bounds': item['bounds'],
            'frame_id': item['frame_id'], 'online': item['online'], 'expected_source': source})
    check(len(releases) == 2 and report['results'][0]['space_id'] == report['results'][1]['space_id'], 'two_versions_belong_to_same_scene')
    check(releases[0]['expected_source']['input_binding']['registration_ref']['package_sha256'] !=
          releases[1]['expected_source']['input_binding']['registration_ref']['package_sha256'], 'versions_have_distinct_original_uploads')
    modes = [('install_first', None), ('activate_first', None), ('restore_first', None),
             ('install_second', None), ('switch_second', None), ('restore_second', None),
             ('rollback_first', None), ('restore_first', 3)]
    space = report['results'][0]['space_id']
    for index, (mode, expected_revision) in enumerate(modes):
        if index == 2:
            Path(releases[0]['bundle']).rename(output / 'v1-export-evidence.zip')
        if index == 5:
            Path(releases[1]['bundle']).rename(output / 'v2-export-evidence.zip')
        prefix = f'{index+1:02d}-{mode}'
        target = output / (prefix + '-result.json')
        request = {'root': str(output / 'consumer'), 'mode': mode, 'space': space,
                   'releases': releases, 'result': str(target)}
        if expected_revision is not None:
            request['expected_revision'] = expected_revision
        path = output / (prefix + '-request.json')
        save(path, request)
        subprocess.run([sys.executable, '-X', 'utf8', '-m', 'experiments.scripts.verify_release_consumption',
                        '--consumer-request', str(path)], check=True, timeout=40,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        value = json.loads(target.read_bytes())
        check(value['network_disabled'], prefix + '_network_disabled')
        if mode != 'install_first':
            second = mode in ('switch_second', 'restore_second')
            check(value['results'] == releases[int(second)]['online'], prefix + '_query_equals_own_online_version')
        processes.append(value)
    check(len({p['pid'] for p in processes}) == 8, 'eight_distinct_consumer_processes')
    check(processes[3]['after']['revision'] == 1 and processes[3]['after']['saved_reference']['publication_id'] == releases[0]['id'], 'installing_second_version_does_not_switch_old_saved_reference')
    check(processes[4]['after']['revision'] == 2 and processes[4]['after']['saved_reference']['publication_id'] == releases[1]['id'], 'explicit_update_saves_revision_two')
    check(processes[6]['after']['revision'] == processes[7]['after']['revision'] == 3
          and processes[7]['after']['saved_reference']['publication_id'] == releases[0]['id'], 'rollback_survives_restart_with_new_revision_three')
    result = {'status': 'passed', 'passed': len(checks), 'checks': checks, 'releases': releases,
              'processes': processes, 'offline_processes': len(processes), 'quality': 'unverified',
              'identity_provider': 'local_mock_only', 'production_ready': False, 'robot_ready': False}
    save(output / 'acceptance.json', result)
    print(json.dumps({'status': 'passed', 'passed': len(checks), 'offline_processes': len(processes)}))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--browser', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    verify(p.parse_args())
