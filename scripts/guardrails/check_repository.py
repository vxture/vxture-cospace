"""Static checks for the imported Python/Vite product repository."""
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    tracked = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    forbidden = ('output/', 'var/', '.venv/', '.playwright-cli/', 'experiments/runs/', 'experiments/evidence/')
    for name in filter(None, tracked):
        path = Path(name)
        assert not name.startswith(forbidden), f'private/generated path tracked: {name}'
        assert not any(p in {'node_modules', '__pycache__'} for p in path.parts), name
        assert not path.name.startswith('.env') or path.name.endswith('.example'), name
        assert path.suffix.lower() not in {'.pem', '.key', '.p12', '.pfx', '.db', '.sqlite'}, name
    for item in json.loads(Path('apps/workbench/vendor/provenance.json').read_text(encoding='utf-8')):
        raw = (Path('apps/workbench/vendor') / item['archive']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['sha256'], item['archive']
    compose = Path('deploy/linux/compose.yml').read_text(encoding='utf-8')
    assert '100.100.197.42' not in compose and '/srv/cospace' not in compose
    assert '${APP_BIND_HOST:?' in compose and '${APP_PUBLISH_PORT:?' in compose
    deploy = Path('.github/workflows/deploy.yml').read_text(encoding='utf-8')
    assert "tags: ['v*.*.*']" in deploy and 'environment: production' in deploy
    assert 'check_deploy_target.py' in deploy
    gate = Path('.github/workflows/ci.yml').read_text(encoding='utf-8')
    watcher = Path('.github/workflows/sca-watch.yml').read_text(encoding='utf-8')
    for text in (gate, watcher):
        assert '2.4.0' in text and '15314940c10d26af9c6649f150b8a47c1262e8fc7e17b1d1029b0e479e8ed8a0' in text
        assert '-L apps/workbench/pnpm-lock.yaml -L uv.lock --config .osv-scanner.toml' in text
    print('repository guardrails passed')


if __name__ == '__main__':
    main()
