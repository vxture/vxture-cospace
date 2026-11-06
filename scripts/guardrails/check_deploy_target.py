"""Fail closed: this product may deploy only to its worker02 production stack."""
import os


def validate(env):
    expected = {
        'DEPLOY_HOST': 'vx-worker-02',
        'STACK_ROOT': '/srv/md0/cospace',
        'PROJECT_NAME': 'cospace',
    }
    for name, value in expected.items():
        if env.get(name) != value:
            raise ValueError(f'{name}: worker02 production configuration required')
    if env.get('DEPLOYMENT_READY') != 'true':
        raise ValueError('DEPLOYMENT_READY: worker02 migration and edge acceptance required')


if __name__ == '__main__':
    try:
        validate(os.environ)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print('worker02 production target accepted')
