import hashlib
import io
import time

import pytest

from packages.infrastructure.ifc_parser_channel import (
    HEADER, SIZE, SOURCE_LIMIT, available, receive_result, receive_source,
)


def test_source_bound_to_digest_and_size(tmp_path):
    raw = b'fixture original'
    digest = hashlib.sha256(raw).digest()
    source, fingerprint = receive_source(io.BytesIO(digest + SIZE.pack(len(raw)) + raw), tmp_path)
    assert source.read_bytes() == raw
    assert fingerprint == digest.hex()
    oversized = io.BytesIO(digest + SIZE.pack(SOURCE_LIMIT + 1))
    with pytest.raises(ValueError, match='source_budget'):
        receive_source(oversized, tmp_path)
    source.unlink()
    tampered = io.BytesIO(b'0'*32 + SIZE.pack(len(raw)) + raw)
    with pytest.raises(ValueError, match='digest'):
        receive_source(tampered, tmp_path)


@pytest.mark.parametrize('name,size,data,error', [
    (b'../ifc.json', 1, b'a', 'channel_member'),
    (b'source.ifc', 1, b'a', 'channel_member'),
    (b'ifc.json', 9*1024*1024, b'a', 'result_budget'),
    (b'ifc.json', 2, b'a', 'truncated'),
])
def test_untrusted_result_cannot_write_paths_or_overrun_limits(tmp_path, name, size, data, error):
    stream = io.BytesIO(SIZE.pack(1) + HEADER.pack(name,size) + data)
    output, source = tmp_path/'out', tmp_path/'source'
    with pytest.raises(ValueError, match=error):
        receive_result(stream, output, source)
    assert not (tmp_path/'ifc.json').exists()


def test_result_keeps_the_worker_original_and_requires_current_readiness(tmp_path):
    import os
    source = tmp_path/'source'
    source.write_bytes(b'worker original')
    output = tmp_path/'out'
    receive_result(io.BytesIO(SIZE.pack(1) + HEADER.pack(b'ifc.json',2) + b'{}'), output, source)
    assert (output/'source.ifc').read_bytes() == b'worker original'
    assert (output/'ifc.json').read_bytes() == b'{}'
    assert not available(source)
    until = time.time()+10
    os.utime(source, (until, until))
    assert available(source)
    assert not available(tmp_path/'missing')
