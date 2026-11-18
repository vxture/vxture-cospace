"""Bounded, path-free transport to the credential-free IFC parser container."""
import hashlib
import re
import shutil
import socket
import struct
import time
from pathlib import Path

SOCKET = Path('/ifc-ipc/parser.sock')
HEARTBEAT = Path('/ifc-ready/worker')
SOURCE_LIMIT = 32 * 1024 * 1024
RESULT_LIMIT = 200 * 1024 * 1024
MAX_MEMBERS = 10_001
PARSE_TIMEOUT = 300
TRANSFER_TIMEOUT = 20
IDLE_HEARTBEAT = 12
ACTIVE_HEARTBEAT = PARSE_TIMEOUT + 2 * TRANSFER_TIMEOUT + 30
HEADER = struct.Struct('!12sI')
SIZE = struct.Struct('!I')
MEMBER = re.compile(rb'ifc\.json|e[0-9]{5}\.npz')


def available(path=None):
    try:
        lease = (path or HEARTBEAT).stat().st_mtime - time.time()
        return 0 < lease <= IDLE_HEARTBEAT
    except OSError:
        return False


def connect(path, timeout):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(timeout)
        client.connect(str(path))
        return client
    except OSError:
        client.close()
        raise


def ping(path=SOCKET):
    try:
        with connect(path, 2) as client:
            client.sendall(b'H')
            return client.recv(1) == b'H'
    except OSError:
        return False


def exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('ifc_channel_truncated')
    return data


class DeadlineReader:
    def __init__(self, client, seconds):
        self.client = client
        self.deadline = time.monotonic() + seconds

    def read(self, size):
        data = bytearray()
        while len(data) < size:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('ifc_channel_deadline')
            self.client.settimeout(remaining)
            part = self.client.recv(size - len(data))
            if not part:
                break
            data.extend(part)
        return bytes(data)


def receive_source(stream, directory):
    digest = exact(stream, 32).hex()
    length, = SIZE.unpack(exact(stream, SIZE.size))
    if not 0 < length <= SOURCE_LIMIT:
        raise ValueError('ifc_channel_source_budget')
    source = directory / 'source.ifc'
    with source.open('xb') as target:
        copy_exact(stream, target, length)
    with source.open('rb') as original:
        if hashlib.file_digest(original, 'sha256').hexdigest() != digest:
            raise ValueError('ifc_channel_digest')
    return source, digest


def copy_exact(stream, target, length):
    while length:
        data = exact(stream, min(length, 256 * 1024))
        target.write(data)
        length -= len(data)


def member_limit(name):
    if not MEMBER.fullmatch(name):
        raise ValueError('ifc_channel_member')
    return (8 if name == b'ifc.json' else 64) * 1024 * 1024


def publish_result(client, result):
    entries = []
    total = 0
    for path in result.iterdir():
        name = path.name.encode('ascii')
        if name in (b'source.ifc', b'inspection-state.json'):
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError('ifc_channel_member')
        size = path.stat().st_size
        total += size
        if not 0 < size <= member_limit(name) or total > RESULT_LIMIT or len(entries) >= MAX_MEMBERS:
            raise ValueError('ifc_channel_result_budget')
        entries.append((path, name, size))
    if not (result/'ifc.json').is_file():
        raise ValueError('ifc_channel_missing_catalog')
    client.sendall(b'R' + SIZE.pack(len(entries)))
    for path, name, size in entries:
        client.sendall(HEADER.pack(name, size))
        with path.open('rb') as stream:
            while data := stream.read(256 * 1024):
                client.sendall(data)


def receive_result(stream, output, source):
    count, = SIZE.unpack(exact(stream, SIZE.size))
    if not 1 <= count <= MAX_MEMBERS:
        raise ValueError('ifc_channel_result_count')
    output.mkdir()
    total = 0
    for _ in range(count):
        raw_name, size = HEADER.unpack(exact(stream, HEADER.size))
        name = raw_name.rstrip(b'\0')
        total += size
        if not 0 < size <= member_limit(name) or total > RESULT_LIMIT:
            raise ValueError('ifc_channel_result_budget')
        with (output / name.decode('ascii')).open('xb') as target:
            copy_exact(stream, target, size)
    if not (output/'ifc.json').is_file():
        raise ValueError('ifc_channel_missing_catalog')
    # Only the worker's own original is used, never bytes returned by native code.
    shutil.copyfile(source, output/'source.ifc')
