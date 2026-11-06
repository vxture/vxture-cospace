"""Read saved sample ownership through the I1 adapter, with synthetic signed identity.

No RP/HTTP login is tested. Never starts jobs, loads geometry, or writes runtime.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time
from joserfc import jwt
from joserfc.jwk import RSAKey
from packages.infrastructure.platform_identity import PlatformVerifierConfig, PlatformTokenVerifier
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.service.platform_resource_access import PlatformResourceAccess
from packages.service.space_access import SpaceAccessPolicy


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(runtime, baseline, output):
    runtime, output = runtime.resolve(), output.resolve()
    if output.is_relative_to(runtime) or runtime.is_relative_to(output) or output.exists():
        raise ValueError('new_separate_output_required')
    original = json.loads(baseline.read_bytes())
    roots = [runtime/name for name in ('preview-builds', 'preview-directory', 'preview-inputs', 'preview-ontologies')]
    def inventory():
        return {p.relative_to(runtime).as_posix(): digest(p) for root in roots for p in root.rglob('*') if p.is_file()}
    before = inventory()
    checks = []
    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})
        if not value: raise AssertionError(name)
    check('historical_managed_files_unchanged', all(digest(Path(p)) == sha for p, sha in original.items()))
    directory = PreviewSpaces.__new__(PreviewSpaces)
    directory.root = runtime/'preview-directory'  # Read only; constructor intentionally bypassed.
    spaces = directory.list('space')
    publications = [json.loads(p.read_bytes()) for p in (runtime/'preview-builds/publications').glob('*/publication.json')]
    bound = [p for p in publications if p.get('space_id') in {s['id'] for s in spaces}]
    check('at_least_two_saved_physical_spaces', len({p['space_id'] for p in bound}) >= 2)
    target = bound[0]['space_id']; issuer = 'https://accounts.vxture.com'
    policy = SpaceAccessPolicy.model_validate({
        'bindings': [{'issuer': issuer, 'space_id': s['id'], 'org_id': 'org_i1_sample', 'workspace_id': 'ws_i1_sample'} for s in spaces],
        'grants': [{'issuer': issuer, 'subject': 'usr_i1_viewer', 'space_id': target, 'role': 'viewer'}],
    })
    key = RSAKey.generate_key(2048, parameters={'kid': 'i1-ephemeral'})
    verifier = PlatformTokenVerifier(PlatformVerifierConfig(issuer=issuer, audience='cospace-i1-local',
        jwks_url=issuer+'/oidc/jwks'), fetch=lambda _: {'keys': [key.as_dict(private=False)]})
    def identity(subject='usr_i1_viewer', workspace='ws_i1_sample', roles=None):
        now = int(time.time())
        token = jwt.encode({'alg': 'RS256', 'kid': key.kid}, {
            'iss': issuer, 'aud': 'cospace-i1-local', 'sub': subject, 'iat': now, 'exp': now+300,
            'userType': 'tenant_user', 'account_status': 'active', 'active_org': 'org_i1_sample',
            'active_workspace': workspace, 'roles': roles or ['workspace:member'],
        }, key)
        return verifier.verify(token)
    user = identity()
    adapter = PlatformResourceAccess(directory, SimpleNamespace(root=runtime/'preview-builds',
        inputs=SimpleNamespace(root=runtime/'preview-inputs')), policy)
    check('visible_list_has_only_explicit_viewer_space', [s['id'] for s in policy.visible(user, spaces)] == [target])
    def denied(name, callback):
        try: callback()
        except PermissionError: check(name, True)
        else: check(name, False)
    for pub in publications:
        artifact = 'publication:'+pub['id']
        if pub.get('space_id') == target:
            check('allow:'+artifact, adapter.artifact(user, artifact, 'space.preview')['space_id'] == target)
            for kind, identity_ in (('candidate', pub['candidate_id']),):
                check('allow:'+kind+':'+identity_, adapter.artifact(user, kind+':'+identity_, 'space.preview')['space_id'] == target)
            denied('viewer_cannot_export:'+artifact, lambda: adapter.artifact(user, artifact, 'space.export'))
            denied('other_user_denied:'+artifact, lambda: adapter.artifact(identity('usr_i1_other'), artifact, 'space.preview'))
            denied('other_workspace_denied:'+artifact, lambda: adapter.artifact(identity(workspace='ws_other'), artifact, 'space.preview'))
        else:
            denied('foreign_or_unassigned_denied:'+artifact, lambda: adapter.artifact(user, artifact, 'space.preview'))
    owner = identity(roles=['workspace:owner'])
    check('owner_sees_only_bound_workspace_spaces', len(policy.visible(owner, spaces)) == len(spaces))
    check('other_workspace_owner_sees_nothing', policy.visible(identity(workspace='ws_other', roles=['workspace:owner']), spaces) == [])
    after = inventory()
    check('runtime_all_managed_files_unchanged', before == after)
    report = {'profile': 'cospace.platform-access-i1-validation/0.1',
        'checked_at': datetime.now(timezone.utc).isoformat(), 'identity_source': 'ephemeral_local_RSA_signature',
        'external_platform_requests': 0, 'rp_login_verified': False, 'http_authorization_enforced': False,
        'historical_files_checked': len(original), 'managed_files_checked': len(before),
        'spaces_read': len(spaces), 'publications_read': len(publications), 'checks': checks,
        'tokens_or_private_keys_saved': False}
    output.mkdir(parents=True)
    for name, value in [('checks.json', report), ('runtime-before.json', before), ('runtime-after.json', after),
                        ('synthetic-policy.json', policy.model_dump())]:
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runtime', type=Path, default=Path('var/nyu'))
    p.add_argument('--baseline', type=Path, default=Path('experiments/evidence/2026-11-03/preview-lifecycle-h3c-001/original-before.json'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); report = verify(a.runtime, a.baseline, a.output)
    print(json.dumps({'passed': len(report['checks']), 'historical_files_checked': report['historical_files_checked'],
        'managed_files_checked': report['managed_files_checked'], 'rp_login_verified': False, 'http_authorization_enforced': False}))


if __name__ == '__main__': main()
