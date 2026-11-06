import pytest
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
