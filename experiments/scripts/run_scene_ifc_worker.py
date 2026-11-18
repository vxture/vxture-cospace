"""Poll the scene IFC queue outside the web service; no web or platform credentials required."""
import argparse
from pathlib import Path
import time

from packages.data.preview_inputs import PreviewInputs
from packages.data.scene_attachments import SceneAttachments
from packages.infrastructure.preview_service_lock import service_guard
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.lifecycle.scene_ifc_versions import SceneIfcVersions, isolated_parser


def drain_one(store, parse):
    pending = []
    for scene in store.inputs.directory.list('space'):
        space = scene['id']
        pending.extend((task['requested_at'], space, task['id']) for task in store.listing(space)['tasks'].values()
                       if task['state'] == 'queued')
    if not pending:
        return False
    _, space, task = min(pending)
    store.run(space, task, parse)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--parser-python', required=True, type=Path)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    executable = args.parser_python.absolute()
    directory = runtime/'preview-directory'
    if not executable.is_file() or not directory.is_dir():
        parser.error('registered_worker_runtime_and_parser_required')
    inputs = PreviewInputs(runtime/'preview-inputs', PreviewSpaces(directory))
    store = SceneIfcVersions(SceneAttachments(inputs))
    parse = isolated_parser(executable)
    with service_guard(inputs.root/'scene-ifc-worker'):
        while True:
            processed = drain_one(store, parse)
            if args.once:
                break
            if not processed:
                time.sleep(2)


if __name__ == '__main__':
    main()
