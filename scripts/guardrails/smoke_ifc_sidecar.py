"""Run the production compose services against disposable Docker volumes."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

PROJECT = 'cospace-ifc-test-' + uuid4().hex[:8]
IMAGE = sys.argv[1]
FIXTURE = Path(sys.argv[2] if len(sys.argv) > 2 else 'tests/fixture_ifc_sidecar.ifc')
SMOKE = Path('tests/container_ifc_smoke.py').read_bytes()
PROBE = 'from packages.infrastructure.ifc_parser_channel import available; raise SystemExit(0 if available() else 1)'


def run(*args, **kwargs):
    return subprocess.run(['docker', *args], timeout=120, **kwargs)


def wait_ready(container, expected):
    for _ in range(20):
        probe = run('exec',container,'python','-c',PROBE)
        if probe.returncode == (0 if expected else 1):
            return
        time.sleep(1)
    raise RuntimeError(f'IFC worker readiness did not become {expected}')


def main(override):
    env = os.environ | {'PROJECT_NAME': PROJECT, 'COSPACE_IMAGE': IMAGE, 'STACK_ROOT': '/unused',
                        'APP_BIND_HOST': '127.0.0.1', 'APP_PUBLISH_PORT': '8088',
                        'COSPACE_PLATFORM_API_URL': 'https://example.invalid'}
    compose = ('compose','-f','deploy/linux/compose.yml','-f',str(override))

    def dc(*args, **kwargs):
        return run(*compose, *args, env=env, check=True, **kwargs)

    try:
        dc('up','-d','--wait','--wait-timeout','60','ifc-parser','ifc-worker')
        worker = dc('ps','-q','ifc-worker',stdout=subprocess.PIPE).stdout.decode().strip()
        parser = dc('ps','-q','ifc-parser',stdout=subprocess.PIPE).stdout.decode().strip()
        details = json.loads(run('inspect',parser,stdout=subprocess.PIPE,check=True).stdout)[0]
        assert {mount['Destination'] for mount in details['Mounts'] if mount['Type'] != 'tmpfs'} == {'/ifc-ipc'}
        run('exec', parser, 'python','-c',
            "import socket; assert socket.if_nameindex()==[(1,'lo')]",
            check=True)
        program = SMOKE.decode()
        run('exec','-i',worker,'python','-c',program,'queue',input=FIXTURE.read_bytes(),check=True)
        for _ in range(90):
            result = run('exec',worker,'python','-c',program,'verify')
            if result.returncode == 0:
                break
            if result.returncode != 3:
                result.check_returncode()
            time.sleep(1)
        else:
            raise RuntimeError('IFC worker did not commit a candidate')
        dc('stop','ifc-parser')
        wait_ready(worker, False)
        dc('up','-d','--wait','--wait-timeout','60','ifc-parser','ifc-worker')
        wait_ready(worker, True)
    except Exception:
        dc('logs','--tail','40','ifc-parser','ifc-worker')
        raise
    finally:
        dc('down','--volumes')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as temp:
        override = Path(temp)/'compose.yml'
        override.write_text('''services:
  ifc-worker:
    volumes:
      - ifc-smoke:/data/runtime
volumes:
  ifc-smoke:
''')
        main(override)
