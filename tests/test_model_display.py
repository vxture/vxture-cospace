from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from packages.construction.model_display import ModelDisplays, byte_range, encoded, identity, BLOCK_BYTES, MAX_RANGE, PROFILE
from packages.construction.preview_model import digest
from packages.service.model_display_http import install
from test_real_model_preview import make_preview


@pytest.fixture
def display(tmp_path):
    root = tmp_path / 'jobs'
    model_root = root / 'build-one/output'
    model_root.mkdir(parents=True)
    make_preview(model_root)
    (model_root / 'human.ply').write_bytes(b'fixed source')
    model = json.loads((model_root / 'model.json').read_bytes())
    model.update(id='build-one', unit='m', axes=['right', 'forward', 'up'],
                 construction={'model_points': 1}, bounds_m=[[0, 0, 2], [0, 0, 2]])
    canonical = model['members']['spatial.npz']['sha256']
    model['members']['human.ply'] = {'sha256': digest(model_root / 'human.ply')}
    model['human_view'] = {'path': 'human.ply', 'source_model_sha256': canonical}
    model['agent_view'].update(path='agent.npz', source_model_sha256=canonical)
    raw = encoded(model)
    (model_root / 'model.json').write_bytes(raw)
    (model_root.parent / 'job.json').write_bytes(encoded({'id': 'build-one', 'state': 'succeeded'}))
    service = ModelDisplays(SimpleNamespace(root=root, directory=None))
    key = identity(raw)
    folder = service.root / key
    folder.mkdir(parents=True)
    payload = bytes(range(256)) * (BLOCK_BYTES // 256 * 2 + 3)
    files = {}
    for name, data in {'metadata.json': b'{"version":"2.0"}', 'hierarchy.bin': b'hierarchy', 'octree.bin': payload}.items():
        (folder / name).write_bytes(data)
        files[name] = {'bytes': len(data), 'sha256': sha256(data).hexdigest(),
                       'blocks': [sha256(data[i:i + BLOCK_BYTES]).hexdigest() for i in range(0, len(data), BLOCK_BYTES)]}
    record = {'profile': PROFILE, 'id': key, 'provider': 'potree/1.8.2',
              'source_manifest_sha256': sha256(raw).hexdigest(), 'source_model_sha256': canonical,
              'files': files, 'block_bytes': BLOCK_BYTES}
    (folder / 'display.json').write_bytes(encoded(record))
    app = FastAPI()
    install(app, service)
    return service, key, folder, model_root, payload, TestClient(app)


@pytest.mark.parametrize('header,expected', [('bytes=0-0', (0, 0)), ('bytes=8-99', (8, 9)),
                                           ('bytes=8-', (8, 9)), ('bytes=-3', (7, 9)), ('bytes=-99', (0, 9))])
def test_http_range_rules(header, expected):
    assert byte_range(header, 10) == expected


@pytest.mark.parametrize('header', [None, 'bytes=-0', 'bytes=999999999-', 'bytes=8-2', 'bytes=0-1,3-4',
                                  'items=0-1', 'bytes=NaN-', 'bytes=--', 'bytes=0-9999999999999999999999999999'])
def test_invalid_or_unbounded_range_rejected(header):
    with pytest.raises(ValueError):
        byte_range(header, MAX_RANGE + 1)


def test_range_crosses_integrity_blocks_without_loading_full_source(display, monkeypatch):
    service, key, _, _, payload, client = display
    # The display read path must not instantiate the full model or decode NPZ.
    monkeypatch.setattr(np, 'load', lambda *a, **k: pytest.fail('full model was decoded'))
    start, end = BLOCK_BYTES - 7, BLOCK_BYTES + 11
    url = f'/candidates/build-one/display/{key}/octree.bin'
    response = client.get(url, headers={'Range': f'bytes={start}-{end}'})
    assert response.status_code == 206
    assert response.content == payload[start:end + 1]
    assert response.headers['content-range'] == f'bytes {start}-{end}/{len(payload)}'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['accept-ranges'] == 'bytes'
    assert len(response.content) == 19
    summary = client.get('/candidates/build-one/api/display').json()
    assert summary['display']['state'] == 'ready' and 'files' not in summary['display']


def test_full_octree_and_multi_range_are_not_silent_full_downloads(display):
    _, key, _, _, payload, client = display
    url = f'/candidates/build-one/display/{key}/octree.bin'
    for headers in ({}, {'Range': 'bytes=0-1,4-5'}, {'Range': f'bytes={len(payload)}-'}):
        response = client.get(url, headers=headers)
        assert response.status_code == 416 and response.content == b''
        assert response.headers['content-range'] == f'bytes */{len(payload)}'


def test_head_and_range_encoding_preserve_native_offsets(display):
    _, key, _, _, _, client = display
    url = f'/candidates/build-one/display/{key}/octree.bin'
    for method in (client.get, client.head):
        response = method(url, headers={'Range': 'bytes=3-11', 'Accept-Encoding': 'gzip'})
        assert response.status_code == 206
        assert response.headers['content-encoding'] == 'identity'
        assert response.headers['content-length'] == '9'
    assert client.head(url, headers={'Range': 'bytes=3-11'}).content == b''


def test_incomplete_integrity_index_fails_closed(display):
    _, key, folder, _, _, client = display
    path = folder / 'display.json'
    info = json.loads(path.read_bytes())
    info['files']['octree.bin']['blocks'].pop()
    path.write_bytes(encoded(info))
    assert client.get(f'/candidates/build-one/display/{key}/octree.bin', headers={'Range': 'bytes=0-3'}).status_code == 409


def test_corrupted_requested_block_is_rejected_and_other_blocks_remain_readable(display):
    _, key, folder, _, _, client = display
    with (folder / 'octree.bin').open('r+b') as stream:
        stream.seek(BLOCK_BYTES + 5)
        stream.write(b'bad')
    url = f'/candidates/build-one/display/{key}/octree.bin'
    assert client.get(url, headers={'Range': 'bytes=0-5'}).status_code == 206
    assert client.get(url, headers={'Range': f'bytes={BLOCK_BYTES}-'}).status_code == 502


def test_changed_model_manifest_cannot_reuse_old_display(display):
    _, key, _, model_root, _, client = display
    model = json.loads((model_root / 'model.json').read_bytes())
    model['label'] = 'new revision'
    (model_root / 'model.json').write_bytes(encoded(model))
    assert client.get(f'/candidates/build-one/display/{key}/octree.bin', headers={'Range': 'bytes=0-3'}).status_code == 409


def test_publication_display_stays_bound_to_its_frozen_manifest(display):
    service, key, _, model_root, _, client = display
    name = 'preview-' + 'a' * 16
    target = service.jobs.root / 'publications' / name
    target.mkdir(parents=True)
    raw = (model_root / 'model.json').read_bytes()
    model = json.loads(raw)
    (target / 'model.json').write_bytes(raw)
    record = {'id': name, 'candidate_id': model['id'], 'model_manifest_sha256': sha256(raw).hexdigest(),
              'source_model_sha256': model['members']['spatial.npz']['sha256']}
    (target / 'publication.json').write_bytes(encoded(record))
    response = client.get(f'/publications/{name}/api/display')
    assert response.status_code == 200 and response.json()['display']['id'] == key
    record['source_model_sha256'] = 'f' * 64
    (target / 'publication.json').write_bytes(encoded(record))
    assert client.get(f'/publications/{name}/api/display').status_code == 409
