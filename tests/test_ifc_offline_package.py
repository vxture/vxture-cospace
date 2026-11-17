import base64
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from packages.spatial.scene_identity import canonical
from packages.views.agent.ifc_offline_package import (
    PackageManifest, export_design_package, inspect_design_package, read_design_package,
)
from test_ifc_workspace import ifc_secured
from test_ifc_structure_http import declare
from test_platform_business import secured, sign_in
from test_platform_login import runtime

ROUTE = '/api/scene-ifc/design-package'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unpack(raw):
    size = struct.unpack_from('<I', raw, 8)[0]
    manifest = json.loads(raw[12:12 + size])
    start = 12 + size
    data = []
    for member in manifest['members']:
        data.append(raw[start:start + member['bytes']])
        start += member['bytes']
    return manifest, data


def pack(manifest, data):
    metadata = canonical(manifest)
    return b'CSIFCP01' + struct.pack('<I', len(metadata)) + metadata + b''.join(data)


def node_read(raw, source):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime unavailable')
    uri = Path('examples/scene-graph/consumers/read-ifc-package.mjs').resolve().as_uri()
    script = ('import {inspectPackage} from ' + json.dumps(uri) + ';'
              "let text='';for await(const chunk of process.stdin){text+=chunk;}const p=JSON.parse(text);"
              "try{process.stdout.write(JSON.stringify(inspectPackage(Buffer.from(p.raw,'base64'),p.expected)));}"
              "catch(e){process.stderr.write(e.message);process.exitCode=1;}")
    payload = {'raw': base64.b64encode(raw).decode(), 'expected': {'sha256': sha(raw), 'source': source}}
    return subprocess.run([node, '--input-type=module', '-e', script], input=json.dumps(payload),
                          text=True, capture_output=True, timeout=30, check=False, shell=False)


@pytest.fixture
def package(ifc_secured):
    env, access, root, config = ifc_secured
    pin = declare(root, config)
    space = env[6][0]['id']
    raw = export_design_package(access.scene_ifc, space, pin)
    source = unpack(raw)[0]['source']
    return raw, source, ifc_secured, space, pin


def test_deterministic_complete_package_and_independent_consumers(package):
    raw, source, (_, access, root, _), space, pin = package
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert export_design_package(access.scene_ifc, space, pin) == raw
    report = inspect_design_package(raw, expected_sha256=sha(raw), expected_source=source)
    assert report['entities'] == 2
    assert report['geometry_components'] == 1
    assert report['without_geometry'] == 1
    assert report['vertices'] == 4
    assert report['real_release_ready'] is False
    loaded = read_design_package(raw, expected_sha256=sha(raw), expected_source=source)
    assert loaded['structure']['entities'][1]['entity_id'] == 'wall'
    assert list(loaded['members']) == ['structure.json', 'e00001.bin']
    assert str(root).encode() not in raw
    result = node_read(raw, source)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == report
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before


@pytest.mark.parametrize('damage', ['magic', 'extra', 'missing', 'duplicate', 'path', 'payload',
                                  'length', 'trailing', 'promote', 'source', 'index', 'order',
                                  'duplicate_json', 'noncanonical', 'unknown_field'])
def test_corrupt_or_incomplete_packages_rejected_by_both_consumers(package, damage):
    raw, source, *_ = package
    manifest, data = unpack(raw)
    if damage == 'magic':
        raw = b'INVALID!' + raw[8:]
    elif damage == 'trailing':
        raw += b'!'
    elif damage in ('duplicate_json', 'noncanonical'):
        metadata = canonical(manifest)
        metadata = (b'{"assessment":"unverified",' + metadata[1:] if damage == 'duplicate_json'
                    else b' ' + metadata)
        raw = raw[:8] + struct.pack('<I', len(metadata)) + metadata + b''.join(data)
    else:
        if damage == 'extra':
            manifest['members'].append({'name': 'e99999.bin', 'bytes': 1, 'sha256': sha(b'x')})
            data.append(b'x')
        elif damage == 'missing':
            manifest['members'].pop()
            data.pop()
        elif damage == 'duplicate':
            manifest['members'].append(manifest['members'][-1])
            data.append(data[-1])
        elif damage == 'path':
            manifest['members'][1]['name'] = '../private.bin'
        elif damage == 'payload':
            data[1] = data[1][:-1] + b'x'
        elif damage == 'length':
            manifest['members'][1]['bytes'] += 1
        elif damage == 'promote':
            manifest['real_release_ready'] = True
        elif damage == 'source':
            manifest['source']['space_id'] = 'space-' + '9' * 16
        elif damage == 'index':
            size = struct.unpack_from('<I', data[1], 8)[0]
            header = json.loads(data[1][12:12 + size])
            start = 12 + size + header['vertices'] * 24
            data[1] = data[1][:start] + struct.pack('<I', header['vertices']) + data[1][start + 4:]
            manifest['members'][1]['sha256'] = sha(data[1])
        elif damage == 'order':
            manifest['members'].reverse()
            data.reverse()
        else:
            manifest['navigation_ready'] = True
        raw = pack(manifest, data)
    digest = sha(raw)
    with pytest.raises(ValueError):
        inspect_design_package(raw, expected_sha256=digest, expected_source=source)
    result = node_read(raw, source)
    assert result.returncode == 1
    assert not result.stdout


def test_external_digest_and_source_pins_required(package):
    raw, source, *_ = package
    digest = sha(raw)
    other_source = source | {'catalog_sha256': '0' * 64}
    with pytest.raises(ValueError, match='byte_digest'):
        inspect_design_package(raw, expected_sha256='0' * 64, expected_source=source)
    with pytest.raises(ValueError, match='source_binding'):
        inspect_design_package(raw, expected_sha256=digest, expected_source=other_source)


@pytest.mark.parametrize('budget', ['MAX_GEOMETRIES', 'MAX_BYTES'])
def test_preflight_refuses_before_loading_mesh(package, monkeypatch, budget):
    _, _, (_, access, _, _), space, pin = package
    monkeypatch.setattr('packages.views.agent.ifc_offline_package.' + budget, 0)
    def never(*args):
        pytest.fail('over-budget package reached geometry encoder')
    monkeypatch.setattr('packages.views.agent.ifc_offline_package.encode_geometry_component', never)
    with pytest.raises(ValueError, match='budget'):
        export_design_package(access.scene_ifc, space, pin)


def test_source_changed_during_batch_is_rejected(package, monkeypatch):
    _, _, (_, access, root, _), space, pin = package
    from packages.views.agent.ifc_offline_package import encode_geometry_component
    def changed(*args):
        data = encode_geometry_component(*args)
        (root / 'source.ifc').write_bytes(b'changed')
        return data
    monkeypatch.setattr('packages.views.agent.ifc_offline_package.encode_geometry_component', changed)
    with pytest.raises(ValueError, match='source_changed'):
        export_design_package(access.scene_ifc, space, pin)


def test_http_authorization_before_storage_and_fixed_download(package, monkeypatch):
    raw, _, (env, access, root, _), space, pin = package
    client = env[1]
    params = {'space_id': space, 'catalog_sha256': pin}
    assert client.get(ROUTE, params=params).status_code == 401
    sign_in(env, 'usr_local_test')
    original = access.scene_ifc.catalog
    def never(*args):
        pytest.fail('unauthorized package reached catalog')
    monkeypatch.setattr(access.scene_ifc, 'catalog', never)
    assert client.get(ROUTE, params=params).status_code == 403
    monkeypatch.setattr(access.scene_ifc, 'catalog', original)
    sign_in(env, 'usr_engineer')
    result = client.get(ROUTE, params=params)
    assert result.status_code == 200, result.text
    assert result.content == raw
    assert result.headers['x-content-sha256'] == sha(raw)
    assert result.headers['cache-control'] == 'no-store'
    head = client.head(ROUTE, params=params)
    assert head.status_code == 200
    assert not head.content
    assert head.headers['x-content-sha256'] == sha(raw)
    for change, status in [({'catalog_sha256': '0' * 64}, 409), ({'catalog_sha256': 'bad'}, 422),
                           ({'root': 'private'}, 422), ({'space_id': env[6][1]['id']}, 403)]:
        assert client.get(ROUTE, params=params | change).status_code == status
    assert client.post(ROUTE, json={}).status_code == 403
    (root / 'e00001.npz').write_bytes(b'changed')
    assert client.get(ROUTE, params=params).status_code == 409


def test_manifest_schema_matches_runtime():
    assert json.loads(Path('contracts/schemas/ifc-design-package-v0.1.schema.json').read_bytes()) == PackageManifest.model_json_schema()
