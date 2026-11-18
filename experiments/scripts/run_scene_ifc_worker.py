"""Poll the scene IFC queue outside the web service; no web or platform credentials required."""
import argparse
import os
from pathlib import Path
from contextlib import contextmanager
from threading import Event, Thread
import time

from packages.data.preview_inputs import PreviewInputs
from packages.data.scene_attachments import SceneAttachments
from packages.infrastructure.ifc_parser_channel import (
    ACTIVE_HEARTBEAT, HEARTBEAT, IDLE_HEARTBEAT, PARSE_TIMEOUT, SIZE, SOCKET,
    DeadlineReader, TRANSFER_TIMEOUT, connect, exact, ping, receive_result,
)
from packages.infrastructure.preview_service_lock import service_guard
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.lifecycle.scene_ifc_versions import ParseFailed, SceneIfcVersions, isolated_parser


def remote_parse(source, output, digest):
    try:
        with connect(SOCKET, TRANSFER_TIMEOUT) as client:
            client.sendall(b'P' + bytes.fromhex(digest) + SIZE.pack(source.stat().st_size))
            with source.open('rb') as original:
                client.sendfile(original)
            status = exact(DeadlineReader(client, PARSE_TIMEOUT + TRANSFER_TIMEOUT), 1)
            if status == b'T':
                raise ParseFailed('parse_timeout')
            if status != b'R':
                raise ParseFailed('parse_rejected')
            receive_result(DeadlineReader(client, TRANSFER_TIMEOUT), output, source)
    except TimeoutError as exc:
        raise ParseFailed('parse_timeout') from exc
    except OSError as exc:
        raise ParseFailed('parser_unavailable') from exc


def pulse(seconds):
    until = time.time() + seconds
    HEARTBEAT.touch()
    os.utime(HEARTBEAT, (until, until))


@contextmanager
def keep_ready():
    stop = Event()
    deadline = time.monotonic() + ACTIVE_HEARTBEAT

    def refresh():
        while not stop.wait(2) and time.monotonic() < deadline:
            pulse(IDLE_HEARTBEAT)

    thread = Thread(target=refresh, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def queue_spaces(store):
    if store.root.is_dir():
        for folder in store.root.iterdir():
            if (store.inputs.directory.root/'space'/f'{folder.name}.json').is_file():
                yield folder.name


def drain_one(store, parse):
    pending = []
    for space in queue_spaces(store):
        pending.extend((task['requested_at'], space, task['id']) for task in store.listing(space)['tasks'].values()
                       if task['state'] == 'queued')
    if not pending:
        return False
    _, space, task = min(pending)
    store.run(space, task, parse)
    return True


def poll(store, parse, *, sidecar, once):
    for space in queue_spaces(store):
        store.recover_interrupted(space)
    while True:
        if sidecar and not ping():
            HEARTBEAT.unlink(missing_ok=True)
            processed = False
        elif sidecar:
            pulse(IDLE_HEARTBEAT)
            with keep_ready():
                processed = drain_one(store, parse)
        else:
            processed = drain_one(store, parse)
        if once:
            return
        if not processed:
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--parser-python', type=Path)
    source.add_argument('--sidecar', action='store_true')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    executable = args.parser_python.absolute() if args.parser_python else None
    directory = runtime/'preview-directory'
    if executable and (not executable.is_file() or not directory.is_dir()):
        parser.error('registered_worker_runtime_and_parser_required')
    inputs = PreviewInputs(runtime/'preview-inputs', PreviewSpaces(directory))
    store = SceneIfcVersions(SceneAttachments(inputs))
    parse = remote_parse if args.sidecar else isolated_parser(executable)
    with service_guard(inputs.root/'scene-ifc-worker'):
        if args.sidecar:
            HEARTBEAT.unlink(missing_ok=True)
        try:
            poll(store, parse, sidecar=args.sidecar, once=args.once)
        finally:
            if args.sidecar:
                HEARTBEAT.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
