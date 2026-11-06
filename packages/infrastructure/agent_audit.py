"""Bounded, read-only inventory. Observations never authorize cleanup/recovery."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3

from packages.data.structure import LiteralIntegerValidator
from packages.infrastructure.agent_files import FilePackages
from packages.infrastructure.files import bounded_read, relative, safe_path
from packages.service.sample import read_json
from packages.views.agent.runtime import SCHEMA, fail


class PackageAudit(FilePackages):
    def __init__(self, root):
        # Do not call the writable constructor, even when root/database is absent.
        self.root = safe_path(root)
        self.path = safe_path(self.root / 'runtime-files.sqlite3')
        if not self.path.is_file():
            fail('store_not_found', 'existing files-backend database required')

    @contextmanager
    def _connect(self):
        safe_path(self.path)
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=5)
        try:
            db.execute('PRAGMA query_only=ON')
            if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                fail('unsupported_store', 'audit requires files-store schema 1')
            db.execute('BEGIN')
            yield db
        finally:
            db.close()

    def scan(self, limit=200):
        if type(limit) is not int or not 1 <= limit <= 1000:
            fail('invalid_limit', 'audit limit must be 1..1000')
        findings, packages, installs, active, directories = [], [], [], [], []

        def finding(code, location, message):
            findings.append({'code': code, 'location': location, 'message': message})

        def rows(db, table, columns):
            result = db.execute(f'SELECT {columns} FROM {table} LIMIT ?', (limit + 1,)).fetchall()
            if len(result) > limit:
                fail('audit_limit', 'database inventory exceeds limit; no partial orphan classification')
            return result

        with self._connect() as db:
            check = db.execute('PRAGMA quick_check(1)').fetchone()[0]
            if check != 'ok':
                fail('store_corrupt', check)
            registered = rows(db, 'packages', 'digest,package_id,scene,manifest')
            installing = rows(db, 'installs', 'install_id,digest,state,revision')
            pointers = rows(db, 'active', 'scene,digest,revision')
            identities = {row[0] for row in registered}
            install_ids = {row[0] for row in installing}
            states = {}
            validator = LiteralIntegerValidator(read_json(SCHEMA.read_bytes()))
            for digest, identity, scene, raw in registered:
                item = {'package_sha256': digest, 'package_id': identity, 'scene_id': scene, 'integrity': 'corrupt'}
                try:
                    manifest = read_json(raw)
                    if next(validator.iter_errors(manifest), None) is not None:
                        fail('structure_error', 'registered manifest does not match runtime schema')
                    manifest, _ = self._load(db, digest)
                    item['integrity'] = 'verified'
                    expected = {'agent-package.json'} | {str(relative(c['member']['path'])) for c in manifest['components']}
                    # Inspect only a bounded tree; never follow links or read extra content.
                    seen = 0
                    def walk_error(error):
                        raise error
                    for current, children, files in os.walk(self._directory(digest), followlinks=False, onerror=walk_error):
                        for name in [*children, *files]:
                            seen += 1
                            if seen > limit:
                                fail('audit_limit', 'package directory inventory exceeds limit')
                            path = Path(current) / name
                            safe_path(path)
                            if path.is_file():
                                logical = path.relative_to(self._directory(digest)).as_posix()
                                if logical not in expected:
                                    finding('extra_member', f'packages/{digest}/{logical}', 'not declared; not read or removed')
                except (ValueError, OSError, KeyError, TypeError, IndexError, AttributeError) as error:
                    item['integrity'] = 'corrupt'
                    finding('package_unreadable', f'packages/{digest}', str(error))
                states[digest] = item['integrity']
                packages.append(item)
            for scene, digest, revision in pointers:
                status = states.get(digest, 'missing_registration')
                if status == 'verified' and next(row[2] for row in registered if row[0] == digest) != scene:
                    status = 'scene_mismatch'
                if type(revision) is not int or revision < 1:
                    status = 'invalid_revision'
                active.append({'scene_id': scene, 'package_sha256': digest, 'revision': revision, 'integrity': status})
                if status != 'verified':
                    finding('active_unusable', f'active/{scene}', status)
            for identity, digest, state, revision in installing:
                installs.append({'install_id': identity, 'package_sha256': digest, 'state': state,
                                 'revision': revision, 'owner_status': 'not_probed'})
                if state in ('copying', 'verified', 'sealed'):
                    finding('nonterminal_installation', f'installs/{identity}', 'may still be running; inspect owner before explicit recovery')
                elif state in ('failed', 'interrupted'):
                    finding('retained_installation', f'installs/{identity}', state)
                elif state != 'ready':
                    finding('invalid_installation_state', f'installs/{identity}', str(state))
                if state == 'ready' and digest not in identities:
                    finding('ready_registration_missing', f'installs/{identity}', 'ready record has no package registration')
            for area in ('packages', 'staging', 'locks'):
                path = self.root / area
                try:
                    safe_path(path)
                    if not path.exists():
                        continue
                    with os.scandir(path) as entries:
                        count = 0
                        for entry in entries:
                            count += 1
                            if count > limit:
                                fail('audit_limit', 'directory inventory exceeds limit')
                            location = area + '/' + entry.name
                            try:
                                safe_path(Path(entry.path))
                                if area == 'packages':
                                    classification = 'registered' if entry.name in identities else 'unregistered_content'
                                    valid_name = bool(re.fullmatch('[0-9a-f]{64}', entry.name))
                                    if classification != 'registered':
                                        finding(classification, location, 'not registered in metadata snapshot; may be an in-flight seal')
                                elif area == 'staging':
                                    classification = 'installation_staging' if entry.name in install_ids else 'unassociated_staging'
                                    valid_name = bool(re.fullmatch('install-[0-9a-f]{32}', entry.name))
                                    finding('retained_staging', location, classification + '; owner not probed')
                                else:
                                    classification = 'lock_evidence'
                                    valid_name = bool(re.fullmatch('install-[0-9a-f]{32}\\.lock', entry.name))
                                if not valid_name or (area != 'locks' and not entry.is_dir(follow_symlinks=False)) or (area == 'locks' and not entry.is_file(follow_symlinks=False)):
                                    finding('unexpected_entry', location, 'unexpected name or type')
                                directories.append({'path': location, 'classification': classification})
                            except (ValueError, OSError) as error:
                                finding('unsafe_entry', location, str(error))
                except (ValueError, OSError) as error:
                    finding('inventory_incomplete', area, str(error))
        complete = not any(f['code'] in ('inventory_incomplete', 'unsafe_entry') or 'exceeds limit' in f['message'] for f in findings)
        healthy = complete and all(item['integrity'] == 'verified' for item in packages + active)
        return {'passed': complete and not findings, 'complete': complete, 'integrity_healthy': healthy,
                'needs_attention': bool(findings), 'robot_ready': False, 'validity': 'unverified_sample_only',
                'observation': 'metadata snapshot; filesystem may change concurrently; no cleanup authorization',
                'packages': packages, 'active': active, 'installations': installs,
                'entries': sorted(directories, key=lambda item: item['path']), 'findings': findings}
