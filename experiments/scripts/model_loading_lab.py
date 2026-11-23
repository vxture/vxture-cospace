"""Loopback-only synthetic L03 comparison surface, excluded from production routing.

Prepare: python -m experiments.scripts.model_loading_lab --prepare --converter PATH
Serve:   python -m experiments.scripts.model_loading_lab
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from experiments.scripts.check_model_display import park
from packages.construction.model_display import ModelDisplays, STRATEGIES, encoded
from packages.service.model_display_http import install
from packages.service.static_assets import WorkbenchAssets

SAMPLES = ('build-display-probe', 'build-linear-probe')
MODEL_MANIFEST = 'model.json'


def prepare(root, converter, points):
    if root.exists():
        raise ValueError('Use a new lab directory; existing fixtures are preserved')
    jobs = SimpleNamespace(root=root / 'preview-builds', directory=None)
    displays = ModelDisplays(jobs, converter)
    fixtures = {}
    for layout in ('grid', 'linear'):
        name = park(jobs.root, points, layout)
        folder = jobs.root / name / 'output'
        model = json.loads((folder / MODEL_MANIFEST).read_bytes())
        (folder / MODEL_MANIFEST).write_bytes(encoded(model))
        displays.build('candidate', name)
        entry = displays.describe('candidate', name)
        with np.load(folder / 'spatial.npz', allow_pickle=False) as source:
            indices = [min(points - 1, i) for i in (4001, 200022, 400033, 700066)]
            anchors = source['points'][indices].tolist()
        displays.exact.build('candidate', name, (entry['display']['source_manifest_sha256'], model['members']['spatial.npz']['sha256']))
        fixtures[name] = {'display': entry['display'], 'anchors': anchors, 'indices': indices,
                          'fixture_manifest_sha256': sha256((folder / MODEL_MANIFEST).read_bytes()).hexdigest()}
    (root / 'fixtures.json').write_bytes(encoded(fixtures))


def create_app(root, assets):
    app = FastAPI()
    displays = ModelDisplays(SimpleNamespace(root=root / 'preview-builds', directory=None))
    install(app, displays)
    fixtures = json.loads((root / 'fixtures.json').read_bytes())

    def fixture_values(sample, strategy, task):
        if sample not in SAMPLES or strategy not in STRATEGIES:
            raise HTTPException(422, 'Invalid synthetic comparison')
        return fixtures[sample] | {'strategy': strategy, 'task': task, 'sample': sample}

    @app.get('/loading-lab', responses={422: {'description': 'Invalid synthetic sample or strategy'}})
    def page(sample: str = SAMPLES[0], strategy: str = 'baseline', task: bool = False):
        fixture_values(sample, strategy, task)
        return FileResponse(Path(__file__).with_suffix('.html'), media_type='text/html',
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.get('/loading-lab/fixture', responses={422: {'description': 'Invalid synthetic sample or strategy'}})
    def fixture(sample: str = SAMPLES[0], strategy: str = 'baseline', task: bool = False):
        return JSONResponse(fixture_values(sample, strategy, task),
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    app.mount('/assets', WorkbenchAssets(directory=str(assets)), name='assets')
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('var/progressive-l03'))
    parser.add_argument('--assets', type=Path, default=Path('var/progressive-l03-build/assets'))
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--converter')
    parser.add_argument('--points', type=int, default=1_000_000)
    parser.add_argument('--port', type=int, default=8794)
    args = parser.parse_args()
    if args.prepare:
        if not args.converter or not 1000 <= args.points <= 10_000_000:
            parser.error('Explicit converter and 1,000–10,000,000 synthetic points required')
        prepare(args.root, args.converter, args.points)
    else:
        import uvicorn
        uvicorn.run(create_app(args.root, args.assets), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
