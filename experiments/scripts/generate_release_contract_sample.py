"""Run from repo root: python -m experiments.scripts.generate_release_contract_sample."""
from pathlib import Path

from packages.service.release_sample import build_release_sample
from packages.service.release_contract import inspect_release_snapshot

if __name__ == '__main__':
    files = build_release_sample()
    report = inspect_release_snapshot(files, now='2026-10-28T00:30:00Z')
    output = Path('examples/spatial-release/synthetic')
    output.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        (output / name).write_bytes(raw)
    print({'generated_files':len(files), 'integrity':report['content_integrity_verified'],
           'authorized':report['authorized'], 'real_release_ready':report['real_release_ready']})
