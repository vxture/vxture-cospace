import json
from pathlib import Path
import pytest
from experiments.scripts.production_workbench import initialize,roots,load_file_secrets,SECRETS
from packages.infrastructure.preview_backup import validate_runtime
from packages.infrastructure.space_policy_store import SpacePolicyStore


def test_explicit_bootstrap_empty_permissions_and_no_overwrite(tmp_path):
    business=tmp_path/'business';initialize(business)
    _,policy=SpacePolicyStore(business/'policy').load()
    assert not policy.bindings and not policy.grants
    assert json.loads((business/'setup/workspace-scenes.json').read_bytes())['workspaces']==[]
    assert json.loads((business/'setup/scene-pointclouds.json').read_bytes())['bindings']==[]
    validate_runtime(business)
    with pytest.raises(ValueError,match='empty_business_root'):initialize(business)
    assert roots(business,tmp_path/'state')==(business,tmp_path/'state')


@pytest.mark.parametrize('business,state',[('relative','/state'),('/', '/state'),('/data','/data/state'),('/state/data','/state')])
def test_roots_are_independent_absolute(business,state):
    with pytest.raises(ValueError):roots(business,state)


def test_file_secrets_no_echo_and_conflicts_fail(tmp_path,monkeypatch):
    for key in SECRETS:
        monkeypatch.delenv(key,raising=False);monkeypatch.delenv(key+'_FILE',raising=False)
    private=tmp_path/'secret';private.write_text('synthetic-secret\n');private.chmod(0o600)
    name=SECRETS[0];monkeypatch.setenv(name,'');monkeypatch.setenv(name+'_FILE',str(private))
    load_file_secrets()
    import os
    assert os.environ[name]=='synthetic-secret'
    with pytest.raises(ValueError,match='private_secret_file_required'):load_file_secrets()
    monkeypatch.delenv(name);private.write_text('secret\nsecond-value')
    with pytest.raises(ValueError,match='single_secret'):load_file_secrets()


def test_container_has_no_secrets_no_public_bind_or_mock_fallback():
    compose=Path('deploy/linux/compose.yml').read_text()
    assert '${APP_BIND_HOST:?' in compose and '${APP_PUBLISH_PORT:?' in compose
    assert '100.100.197.42' not in compose and '0.0.0.0:' not in compose
    assert '${STACK_ROOT:?' in compose and '/srv/cospace' not in compose
    assert 'read_only: true' in compose and 'user: "10001:10001"' in compose
    assert 'COSPACE_OIDC_CLIENT_SECRET:' not in compose and 'COSPACE_SESSION_KEY:' not in compose
    assert 'cospace-platform' not in compose and 'mock' not in compose
    assert 'COSPACE_PLATFORM_WEBHOOK_SECRET_FILE' in compose
    nginx=Path('deploy/linux/cospace.nginx.conf').read_text()
    assert 'server_name cospace.ruyin.work;' in nginx and 'access_log off;' in nginx
    assert 'client_max_body_size 128m' in nginx and 'client_max_body_size 64k' in nginx


def test_allowlisted_bundle_contains_no_business_data_or_secret_files(tmp_path):
    from experiments.scripts.package_production import package
    import tarfile
    root=tmp_path/'repo';paths={
        'apps/workbench/dist/layout.html':b'<html/>','deploy/linux/requirements.lock':b'',
        'packages/code.py':b'pass','var/secret':b'private','tests/test_fixture.py':b'pass',
        '.git/config':b'private','output/leaked-token.json':b'private',
    }
    for name,raw in paths.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    result=package(root,tmp_path/'software.tar.gz','test-release')
    with tarfile.open(result['bundle']) as archive:
        assert set(archive.getnames())=={'apps/workbench/dist/layout.html','deploy/linux/requirements.lock','packages/code.py','release.json'}
        manifest=json.loads(archive.extractfile('release.json').read())
        assert manifest['business_data_included'] is manifest['secrets_included'] is False
    with pytest.raises(FileExistsError):package(root,tmp_path/'software.tar.gz','test-release')
