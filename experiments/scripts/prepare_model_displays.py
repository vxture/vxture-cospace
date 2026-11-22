"""Offline display backfill/retry; requires exclusive ownership of the runtime."""
import argparse
from pathlib import Path
from types import SimpleNamespace

from packages.construction.model_display import ModelDisplays
from packages.infrastructure.preview_service_lock import service_guard
from packages.lifecycle.preview_spaces import PreviewSpaces


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--converter', type=Path)
    parser.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args()
    root = args.runtime.resolve()
    if not (root / 'preview-builds').is_dir():
        parser.error('existing_runtime_required')
    with service_guard(root):
        jobs = SimpleNamespace(root=root / 'preview-builds', directory=PreviewSpaces(root / 'preview-directory'))
        displays = ModelDisplays(jobs, args.converter)
        if not displays.converter:
            parser.error('converter_required')
        if args.retry_failed:
            for failure in displays.root.glob('*.error.json'):
                failure.unlink()
        displays.scan()
        print('Display backfill finished; inspect derivative error records before resuming service.')


if __name__ == '__main__':
    main()
