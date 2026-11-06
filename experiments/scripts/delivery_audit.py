"""Read-only synthetic delivery diagnostics; independent observations, never permission."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
import sys
import time
import uuid

from experiments.scripts.recovery_audit import RecoveryAudit
from experiments.scripts.recovery_journal import APP_ID
from packages.infrastructure.agent_audit import PackageAudit
from packages.infrastructure.files import safe_path, bounded_read
from packages.data.imports import canonical, sha
from packages.service.sample import read_json
from packages.data.delivery_report import ReportGeneration, generation_context


class DeliveryAudit:
    def __init__(self, files_root, journal_root):
        self.files_root, self.journal_root = files_root, journal_root

    def scan(self, binding, limit=100):
        started = datetime.now(timezone.utc)
        monotonic = time.monotonic_ns()
        report_id = str(uuid.uuid4())
        report = self._scan(binding, limit)
        context = generation_context(report, self.files_root, self.journal_root, limit)
        finished = datetime.now(timezone.utc)
        stamp = lambda value: value.isoformat(timespec='microseconds').replace('+00:00', 'Z')
        metadata = ReportGeneration.model_validate({
            'schema_version': 'cospace.delivery-generation/0.1', 'report_id': report_id,
            'producer': {'name': 'cospace.delivery-audit', 'version': '0.2'},
            'interval': {'started_at': stamp(started), 'finished_at': stamp(finished),
                         'elapsed_ms': (time.monotonic_ns() - monotonic) // 1_000_000,
                         'clock': 'system_utc_untrusted', 'wall_end_before_start': finished < started,
                         'consistency': 'independent_readonly_snapshots'}, **context})
        report['generation'] = metadata.model_dump()
        return report

    def _scan(self, binding, limit):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('limit must be 1..200')
        binding = read_json(canonical(binding))
        keys = {'scene_id','release_id','truth_version_id','view_version_id','package_sha256',
                'release_sha256','truth_sha256','view_sha256','profile','scope_sha256'}
        if (not isinstance(binding, dict) or set(binding) != keys
                or any(not isinstance(v, str) or not 1 <= len(v) <= 128 for v in binding.values())):
            raise ValueError('complete fixed binding required')
        findings = []
        def issue(code, component, action):
            findings.append({'code': code, 'component': component, 'next_action': action})
        try:
            auditor = PackageAudit(self.files_root)
            package_report = auditor.scan(limit)
        except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as error:
            package_report = {'complete': False, 'needs_attention': True, 'findings': [{'code': getattr(error, 'code', 'store_unreadable')}]}
        recovery_report = RecoveryAudit(self.journal_root).scan(limit)
        for component, report in [('files', package_report), ('journal', recovery_report)]:
            if not report['complete']:
                issue('observation_incomplete', component, '保留现场，检查路径、格式、限额和读取诊断后重新核对')
            elif report['needs_attention']:
                issue('component_needs_attention', component, '核对组件诊断；恢复或安装处理须走独立受控流程，不自动清理')
        observed = {'file_binding': None, 'journal_binding': None, 'active_revision': None,
                    'binding_match': False, 'journal_status': 'not_checked'}
        try:
            # A separate fresh read; compare against the earlier inventory, do not pretend atomicity.
            auditor = PackageAudit(self.files_root)
            with auditor._connect() as db:
                active = db.execute('SELECT digest,revision FROM active WHERE scene=?', (binding['scene_id'],)).fetchone()
                if active is None:
                    raise ValueError('active_package_missing')
                manifest, _ = auditor._load(db, active[0])
                source = manifest['source']
                expected = {k: source[k] for k in keys if k not in ('package_sha256', 'profile', 'scope_sha256')}
                expected.update(package_sha256=active[0], profile=manifest['profile'], scope_sha256=sha(canonical(manifest['scope'])))
                observed.update(file_binding=expected, active_revision=active[1])
                earlier = next((r for r in package_report.get('active', []) if r['scene_id'] == binding['scene_id']), None)
                if earlier is None or (earlier['package_sha256'], earlier['revision']) != tuple(active):
                    issue('file_observation_changed', 'files', '活动指针观察不一致，重新核对；报告不建立跨库快照')
                if expected != binding:
                    issue('file_binding_mismatch', 'binding', '核对所选场景和目标完整版本绑定，不能借用其他包的证明')
        except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as error:
            issue('file_binding_unavailable', 'binding', '检查目标活动包及文件完整性；保留损坏内容供诊断')
        try:
            path = safe_path(safe_path(self.journal_root) / 'journal-test.sqlite3')
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
                db.execute('PRAGMA query_only=ON')
                db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 256 * 1024)
                budget = [1000]
                def progress():
                    budget[0] -= 1
                    return int(budget[0] <= 0)
                db.set_progress_handler(progress, 1000)
                db.execute('BEGIN')
                if db.execute('PRAGMA application_id').fetchone()[0] != APP_ID or db.execute('PRAGMA user_version').fetchone()[0] != 3:
                    raise ValueError('unsupported_store')
                control = db.execute('SELECT store_id,context,generation,mode,revision,state_sha256 FROM control').fetchmany(2)
                reference = recovery_report['control']
                if len(control) != 1 or reference is None or tuple(reference.values()) != control[0]:
                    issue('journal_observation_changed', 'journal', '恢复元数据观察不一致，重新生成报告')
                # deployment is not inferred from unsigned binding; match the full stored binding directly.
                rows = db.execute('SELECT binding,content IS NOT NULL,status IS NOT NULL,grant_proof IS NOT NULL FROM states LIMIT ?', (limit + 1,)).fetchall()
                if len(rows) > limit:
                    raise ValueError('audit_limit')
                matching = [row for row in rows if read_json(row[0]) == binding]
                if len(matching) != 1:
                    issue('journal_binding_missing_or_ambiguous', 'binding', '通过独立受控接收流程核对目标包证明，不能复制旧包授权')
                else:
                    row = matching[0]
                    observed['journal_binding'] = read_json(row[0])
                    observed['journal_status'] = 'proof_fields_present_unverified' if all(row[1:]) else 'proof_fields_missing'
                    if not all(row[1:]):
                        issue('proof_fields_missing', 'journal', '核对内容、状态和grant是否齐备；不得据字段存在推定有效')
        except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
            issue('journal_binding_unavailable', 'binding', '检查实验日志格式、读取限额及固定版本记录')
        observed['binding_match'] = observed['file_binding'] == binding == observed['journal_binding']
        return {'schema_version': 'cospace.test-delivery-audit/0.2', 'test_only': True,
            'requested_binding': binding, 'observed': observed,
            'complete': package_report['complete'] and recovery_report['complete'] and not any(
                f['code'] in ('file_binding_unavailable','journal_binding_unavailable','file_observation_changed','journal_observation_changed') for f in findings),
            'needs_attention': bool(findings), 'findings': findings,
            'components': {'files': package_report, 'journal': recovery_report},
            'validity': 'not_evaluated', 'proofs_verified': False, 'history_verified': False,
            'authorized': False, 'robot_ready': False, 'repair_authorized': False,
            'observation': 'independent read-only snapshots; filesystem and stores may change; no delivery acceptance or runtime permission'}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', required=True)
    parser.add_argument('--journal', required=True)
    parser.add_argument('--binding', required=True)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    try:
        report = DeliveryAudit(args.files, args.journal).scan(read_json(bounded_read(args.binding)), args.limit)
    except (ValueError, OSError) as error:
        print(json.dumps({'error': str(error), 'authorized': False, 'repair_authorized': False}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['complete'] and not report['needs_attention'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
