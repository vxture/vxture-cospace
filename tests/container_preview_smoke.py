"""Run in the built image, without mounting the source tree or test fixtures."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace

import numpy as np

from packages.construction.preview_derivations import PIPELINE, SplitBuilds, freeze, write
from packages.construction.preview_model import PreviewModel


def main():
    with TemporaryDirectory(prefix='cospace-image-smoke-') as temporary:
        root = Path(temporary)
        identity = 'build-container-smoke'
        job_root = root / identity
        frozen = job_root / 'frozen'
        frozen.mkdir(parents=True)
        points = np.array([[.05, .05, .05], [.25, .25, .25]], dtype=np.float32)
        colors = np.array([[10, 20, 30], [80, 90, 100]], dtype=np.uint8)
        np.savez_compressed(frozen / 'spatial.npz', points=points, colors=colors)
        scope = {'space_id': 'space-container-smoke', 'project_id': 'project-container-smoke'}
        metadata = {
            'id': identity, 'source': {'input_binding': {}}, 'frame_id': 'synthetic_anchor',
            'unit': 'm', 'axes': ['x', 'y', 'z'], 'data_kind': 'synthetic_image_smoke',
            'construction': {'input_frames': 1, 'used_frames': 1, 'model_points': 2},
            'bounds_m': [[.05] * 3, [.25] * 3], 'quality': {'grade': 'unverified'},
            'real_release_ready': False, 'robot_ready': False, **scope,
        }
        freeze(frozen, metadata)
        job = {'id': identity, 'state': 'running', 'stage': 'building_model',
               'pipeline': PIPELINE, 'input_binding': {}, **scope}
        jobs = SimpleNamespace(root=root, save=lambda record: write(job_root / 'job.json', record))
        jobs.save(job)
        split = SplitBuilds(jobs)
        split.begin(job)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            split.poll()
            current = json.loads((job_root / 'job.json').read_bytes())
            if current['state'] != 'running':
                break
            time.sleep(.1)
        assert current['state'] == 'succeeded', current
        model = PreviewModel(job_root / 'output')
        assert model.query([.05, .05, .05])['state'] == 'surface_candidate'
        assert model.query([10, 10, 10])['state'] == 'unknown'
        assert (model.root / 'index.html').is_file()
        assert (model.root / 'index.html').read_bytes() == Path(
            'experiments/templates/nyu-flow-preview.html').read_bytes()
        assert set(model.manifest['derivation']['views']) == {'human', 'agent'}
        print('Production image: model freeze, real view subprocesses, composition and preview passed')


if __name__ == '__main__':
    main()
