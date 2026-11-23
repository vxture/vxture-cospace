"""Installable ontology host acceptance outside the checkout, with ephemeral state."""
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from queue import Queue
import re
import secrets
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


DEFINITIONS = '/api/ontology-definitions'
GROUPS = '/api/ontology-configuration/groups'
DIRECTORY = '/api/ontology-directory'
MODULE = 'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module("vxture_ontology.local_host",run_name="__main__")'


@contextmanager
def start(command, data, config, cwd):
    with subprocess.Popen([*command, 'serve', '--data-dir', str(data), '--identity-config', str(config),
                           '--port', '0'], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8') as process:
        line = Queue()
        Thread(target=lambda: line.put(process.stdout.readline()), daemon=True).start()
        try:
            first = line.get(timeout=15).strip()
            assert re.fullmatch(r'Listening at http://127\.0\.0\.1:[0-9]+', first), 'startup failed'
            origin = first.removeprefix('Listening at ')
            opener = build_opener(ProxyHandler({}))

            def request(path, token=None, body=None, *, headers=None, status=200):
                request_headers = {**({'Authorization': 'Bearer ' + token} if token else {}), **(headers or {})}
                payload = None
                if body is not None:
                    request_headers.update({'Content-Type': 'application/json'})
                    payload = json.dumps(body).encode('utf-8')
                req = Request(origin + path, headers=request_headers, data=payload)
                try:
                    response = opener.open(req, timeout=10)
                except HTTPError as exc:
                    response = exc
                with response:
                    assert response.status == status, (path, response.status, status)
                    assert response.headers['Cache-Control'] == 'no-store'
                    return json.load(response)

            yield request
        finally:
            process.terminate()
            _, errors = process.communicate(timeout=15)
            assert not errors, 'unexpected server error output'


def run(command, cwd, *arguments, expected=0):
    result = subprocess.run([*command, *map(str, arguments)], cwd=cwd,
                            capture_output=True, timeout=20, check=False)
    assert result.returncode == expected, (arguments[0], result.returncode)


def acceptance(command, root):
    roles = {
        'writer': ('yard', ['read', 'read_private', 'edit', 'submit']),
        'reviewer': ('yard', ['read', 'read_private', 'review']),
        'publisher': ('yard', ['read', 'publish']),
        'reader': ('yard', ['read']),
        'other': ('other-yard', ['read']),
        'operator': ('yard', ['configure_groups']),
    }
    tokens = {actor: secrets.token_urlsafe(32) for actor in roles}
    config = root / 'identity.json'
    record = {'profile': 'vxture.ontology-local-host/0.1', 'principals': [
        {'scope': scope, 'actor': actor, 'permissions': grants,
         'token_sha256': sha256(tokens[actor].encode()).hexdigest()} for actor, (scope, grants) in roles.items()]}
    config.write_text(json.dumps(record), encoding='utf-8')
    data, backup, recovered = (root / name for name in ('state', 'backup', 'recovered'))
    author, reviewer, publisher = (tokens[key] for key in ('writer', 'reviewer', 'publisher'))
    reader, other, operator = (tokens[key] for key in ('reader', 'other', 'operator'))
    module_read = DEFINITIONS + '?module_id=core'
    with start(command, data, config, root) as call:
        assert call(DIRECTORY, status=401)['detail'] == 'authentication_required'
        call(DIRECTORY, reader, headers={'Origin': 'https://other.example'}, status=403)
        call(DIRECTORY, reader, headers={'Host': 'other.example'}, status=403)
        call(GROUPS, reader, status=403)
        call(module_read, operator, status=403)
        call(module_read + '&module_id=water', reader, status=422)
        bundle = call(module_read, author)['source_bundle']
        save = dict(action='save', request_id='a' * 32, module_id='core', expected_revision=0,
                    bundle=bundle, base_reference=None)
        call(DEFINITIONS, reader, save, status=403)
        call(DEFINITIONS, author, {**save, 'actor': 'reviewer', 'scope': 'other-yard'}, status=422)
        assert call(DEFINITIONS, author, save)['revision'] == 1
        pending = call(DEFINITIONS, author, dict(action='submit', request_id='b' * 32, module_id='core',
                                               expected_revision=1))
        assert not call(module_read, reader)['reviews']
        assert call(DEFINITIONS + '?' + urlencode({'review_id': pending['review_id']}), reader, status=403)
        settings = call(GROUPS, operator)
        created = call(GROUPS, operator, dict(request_id='e' * 32, expected_revision=settings['revision'],
                       group_id=None, name='Site systems', description='', sort_order=0,
                       status='active', reason='synthetic grouping'))
        group = next(g for g in created['groups'] if g['name'] == 'Site systems')
        moved = call(GROUPS, operator, dict(request_id='f' * 32, expected_revision=created['revision'],
                     group_id=group['group_id'], move='top', reason='synthetic ordering'))
        assert moved['groups'][0]['group_id'] == group['group_id']
        run(command, root, 'backup', '--data-dir', data, '--output-dir', backup)

    decision = dict(action='decide', request_id='c' * 32, review_id=pending['review_id'],
                    decision='approved', reason='synthetic review')
    publish = dict(action='publish', request_id='d' * 32, review_id=pending['review_id'], expected_revision=1)
    with start(command, data, config, root) as call:
        assert call(module_read, reviewer)['reviews'][0]['can_decide']
        assert call(DEFINITIONS, author, save)['revision'] == 1  # persisted idempotency
        assert call(GROUPS, operator)['revision'] == moved['revision']
        call(DEFINITIONS, author, decision, status=403)
        call(DEFINITIONS, publisher, publish, status=409)
        call(DEFINITIONS, reviewer, decision)
        release = call(DEFINITIONS, publisher, publish)
        exact_path = DEFINITIONS + '?' + urlencode(release['reference'])
        assert call(exact_path, reader)['modules'][0]['reference'] == release['reference']
        assert call(module_read, other)['releases'] == []
        bundle['modules'][0]['version'] = '0.2.0'
        call(DEFINITIONS, author, dict(save, request_id='1' * 32, expected_revision=1,
                                      base_reference=release['reference'], bundle=bundle))
        newer = call(DEFINITIONS, author, dict(action='submit', request_id='2' * 32,
                                             module_id='core', expected_revision=2))
        call(DEFINITIONS, reviewer, dict(decision, request_id='3' * 32, review_id=newer['review_id']))
        latest = call(DEFINITIONS, publisher, dict(publish, request_id='4' * 32, review_id=newer['review_id'],
                                                  expected_revision=2))
        shown = next(e for e in call(DIRECTORY, reader)['modules'] if e['reference']['module_id'] == 'core')
        assert shown['reference'] == latest['reference'] and shown['published_at'] == latest['published_at']
        assert call(exact_path, reader)['modules'][0]['reference'] == release['reference']
        published_backup = root / 'published-backup'
        run(command, root, 'backup', '--data-dir', data, '--output-dir', published_backup)

    assert {p.name for p in backup.iterdir()} == {'ontology-host.sqlite3'}
    run(command, root, 'restore', '--backup-dir', backup, '--data-dir', data, expected=1)
    run(command, root, 'restore', '--backup-dir', backup, '--data-dir', recovered)
    with start(command, recovered, config, root) as call:
        assert call(module_read, reviewer)['reviews'][0]['state'] == 'pending'
        assert call(module_read, reader)['releases'] == []
        assert call(GROUPS, operator)['groups'][0]['group_id'] == group['group_id']

    restored_release = root / 'restored-release'
    run(command, root, 'restore', '--backup-dir', published_backup, '--data-dir', restored_release)
    with start(command, restored_release, config, root) as call:
        assert call(exact_path, reader)['modules'][0]['reference'] == release['reference']
        assert [r['reference']['version'] for r in call(module_read, reviewer)['releases']] == ['0.2.0', '0.1.0']
    print(json.dumps({'isolated_host': True, 'live_backup_and_restore': True, 'fixed_release': True}))


if __name__ == '__main__':
    wheel = Path(sys.argv[1]).resolve()
    with TemporaryDirectory(prefix='ontology-host-') as directory:
        acceptance([sys.executable, '-I', '-S', '-c', MODULE, str(wheel)], Path(directory))
