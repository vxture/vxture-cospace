"""Repeat the loopback loading lab through Playwright CLI; evidence stays in output/.

Open a dedicated playwright-cli session at http://127.0.0.1:8794/loading-lab first.
Default three repeats are a pilot, NOT the 30 repeats per condition enablement gate.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import time
from urllib.parse import urlencode

from experiments.scripts.model_loading_lab import SAMPLES

STRATEGIES = ('baseline', 'task', 'adaptive', 'governance', 'combined')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', default='l03-loading')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--seed', type=int, default=9003)
    parser.add_argument('--output', type=Path, default=Path('output/l03-comparison'))
    parser.add_argument('--npx-script', type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    if not args.output.resolve().is_relative_to(root / 'output') or not 1 <= args.rounds <= 100:
        parser.error('Use output/ and 1–100 repeats per condition')
    args.output.mkdir(parents=True, exist_ok=False)
    node = shutil.which('node')
    if not node:
        parser.error('Node.js with npm/npx is required')
    npx = args.npx_script or Path(node).parent / 'node_modules/npm/bin/npx-cli.js'
    if not npx.is_file():
        parser.error('Provide npm/bin/npx-cli.js with --npx-script')
    command = [node, str(npx), '--yes', '--package', '@playwright/cli', 'playwright-cli', '-s=' + args.session]
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

    def cli(*values):
        result = subprocess.run(command + list(values), capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=150, creationflags=flags)
        if result.returncode or '### Error' in result.stdout:
            raise RuntimeError((result.stdout + result.stderr)[-3000:])
        return result.stdout

    runtime = root / 'apps/workbench/public/assets/pointcloud-runtime'
    scripts = Path('experiments/scripts')
    evidence = {'pilot': args.rounds < 30, 'repeats_per_condition': args.rounds, 'seed': args.seed,
                'assets': {p.name: sha256(p.read_bytes()).hexdigest() for p in runtime.glob('*.js')},
                'scripts': {name: sha256((scripts / name).read_bytes()).hexdigest()
                            for name in ('model_loading_lab.html', 'model_loading_probe.js')},
                'network': '5Mbps/100ms/all cold', 'viewport': '1920x1080/DPR1', 'rows': []}
    rng = random.Random(args.seed)
    for repeat in range(args.rounds):
        order = [(sample, strategy) for sample in SAMPLES for strategy in STRATEGIES]
        rng.shuffle(order)
        for sample, strategy in order:
            started = time.monotonic()
            cli('goto', 'http://127.0.0.1:8794/loading-lab?' + urlencode({'sample': sample, 'strategy': strategy, 'task': 'true'}))
            raw = cli('run-code', '--filename', 'experiments/scripts/model_loading_probe.js')
            (args.output / f'{repeat}-{sample}-{strategy}.txt').write_text(raw, encoding='utf-8')
            found = re.search(r'^### Result\r?\n([^\r\n]+)', raw, re.M)
            if not found:
                raise RuntimeError('No measured result; inspect retained evidence')
            row = json.loads(found[1]) | {'repeat': repeat}
            evidence['rows'].append(row)
            (args.output / 'results.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print(json.dumps({'repeat': repeat, 'sample': sample, 'strategy': strategy,
                              'seconds': round(time.monotonic() - started, 1), **row['metrics']}), flush=True)


if __name__ == '__main__':
    main()
