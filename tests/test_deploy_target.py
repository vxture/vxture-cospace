import pytest
from pathlib import Path
from scripts.guardrails.check_deploy_target import validate


GOOD = dict(DEPLOY_HOST='vx-worker-02', STACK_ROOT='/srv/md0/cospace',
            PROJECT_NAME='cospace', DEPLOYMENT_READY='true')


def test_worker02_target():
    validate(GOOD)


@pytest.mark.parametrize('key,value', [
    ('DEPLOY_HOST', 'vx-worker-01'), ('DEPLOY_HOST', '39.103.62.17'),
    ('STACK_ROOT', '/srv/cospace'), ('STACK_ROOT', '/srv/md0/vxtpl'),
    ('PROJECT_NAME', 'vxtpl'), ('DEPLOYMENT_READY', 'false'),
    ('DEPLOYMENT_READY', ''),
])
def test_reject_wrong_host_scope_or_unaccepted_migration(key, value):
    with pytest.raises(ValueError):
        validate({**GOOD, key: value})


def test_deploy_checks_private_state_without_relaxing_permissions():
    script = (Path(__file__).resolve().parents[1] / 'deploy/deploy.sh').read_text()
    assert 'sudo -n test -f "$STACK_ROOT/etc/secrets/$key"' in script
    assert 'sudo -n test -f "$STACK_ROOT/data/business/setup/workspace-scenes.json"' in script
    assert 'chmod' not in script


def test_registry_access_is_temporary_and_fallback_is_independent():
    script = (Path(__file__).resolve().parents[1] / 'scripts/workflows/deploy-worker02.sh').read_text()
    assert 'DOCKER_CONFIG="$(mktemp -d /tmp/cospace-registry.XXXXXXXX)"' in script
    assert 'trap cleanup EXIT' in script
    assert 'for attempt in 1 2 3' in script
    assert 'login_registry ghcr.io' in script
    assert 'login_registry "$ACR_REGISTRY"' in script
