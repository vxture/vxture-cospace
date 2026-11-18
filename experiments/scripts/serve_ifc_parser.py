"""Private parser sidecar. Its only shared mount is the Unix socket directory."""
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import tempfile

from packages.infrastructure.ifc_parser_channel import (
    SOCKET, DeadlineReader, PARSE_TIMEOUT, TRANSFER_TIMEOUT, exact, publish_result, receive_source,
)

NATIVE = '/opt/ifc/bin/python'


def native_result(source, result, digest):
    with subprocess.Popen(
        [NATIVE, '-m', 'experiments.scripts.parse_scene_ifc', str(source), str(result), digest],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    ) as run:
        try:
            return b'F' if run.wait(timeout=PARSE_TIMEOUT) else b'R'
        except subprocess.TimeoutExpired:
            return b'T'
        finally:
            try:
                os.killpg(run.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def serve_one(client):
    stream = DeadlineReader(client, TRANSFER_TIMEOUT)
    try:
        command = exact(stream, 1)
        if command == b'H':
            client.sendall(b'H')
            return
        if command != b'P':
            raise ValueError('ifc_channel_command')
        with tempfile.TemporaryDirectory(prefix='ifc-parser-') as temp:
            source, digest = receive_source(stream, Path(temp))
            result = Path(temp) / 'result'
            status = native_result(source, result, digest)
            client.settimeout(TRANSFER_TIMEOUT)
            if status == b'R':
                publish_result(client, result)
            else:
                client.sendall(status)
    except (OSError, ValueError):
        # Closing a partial stream makes the worker reject the entire result.
        return


def main():
    os.umask(0o077)
    subprocess.run([NATIVE, '-c', 'import ifcopenshell.geom'], check=True, timeout=20)
    if SOCKET.exists() and not stat.S_ISSOCK(SOCKET.lstat().st_mode):
        raise ValueError('ifc_channel_socket_expected')
    SOCKET.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(SOCKET))
        listener.listen(2)
        while True:
            client, _ = listener.accept()
            with client:
                serve_one(client)


if __name__ == '__main__':
    main()
