import hashlib
import base64
import json
from pathlib import Path
import shutil
import struct
import subprocess

import numpy as np
import pytest

from packages.data.ifc_inspection import digest
from packages.data.ifc_workspace import load_mesh
from packages.spatial.scene_identity import canonical
from packages.views.agent.ifc_geometry_exchange import (
    GeometryHeader, build_geometry_component, inspect_geometry_component, geometry_summary,
)
from packages.views.agent.ifc_structure_exchange import build_structure_snapshot
from test_ifc_structure_review import structure_source
from test_ifc_workspace import ifc_secured
from test_ifc_structure_http import declare
from test_platform_business import secured, sign_in
from test_platform_login import runtime

SPACE = 'space-' + '1' * 16
ROUTE = '/api/scene-ifc/element-geometry'


def node_read(raw, args):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime unavailable')
    uri = Path('examples/scene-graph/consumers/read-ifc-geometry.mjs').resolve().as_uri()
    script = ("import {readGeometry} from " + json.dumps(uri) + ";"
              "let input='';for await(const chunk of process.stdin){input+=chunk;}"
              "const p=JSON.parse(input);try{const result=readGeometry(Buffer.from(p.raw,'base64'),"
              "Buffer.from(p.structure,'base64'),p.expected);"
              "process.stdout.write(JSON.stringify(result.summary));}"
              "catch(e){process.stderr.write(e.message);process.exitCode=1;}")
    payload = dict(raw=base64.b64encode(raw).decode(),
                   structure=base64.b64encode(args['structure_raw']).decode(),
                   expected=dict(sha256=args['expected_sha256'],
                                 structureSha256=args['expected_structure_sha256'],
                                 source=args['expected_source'], element=args['expected_element']))
    return subprocess.run([node, '--input-type=module', '-e', script], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=20, check=False, shell=False)


def fixture_component(env):
    root, catalog = env
    pin = digest(root / 'ifc.json')
    declaration = build_structure_snapshot(SPACE, pin, catalog)
    raw = build_geometry_component(root, SPACE, pin, catalog, 'e00001')
    return raw, dict(expected_sha256=hashlib.sha256(raw).hexdigest(), structure_raw=declaration,
                     expected_structure_sha256=hashlib.sha256(declaration).hexdigest(),
                     expected_source=json.loads(declaration)['source'], expected_element='e00001')


def test_full_mesh_roundtrip_is_deterministic_and_bound(structure_source):
    raw, args = fixture_component(structure_source)
    header, vertices, faces = inspect_geometry_component(raw, **args)
    original_v, original_f = load_mesh(structure_source[0], structure_source[1]['products'][1])
    assert np.array_equal(vertices, original_v)
    assert np.array_equal(faces, original_f)
    assert fixture_component(structure_source)[0] == raw
    summary = geometry_summary(header, vertices, faces)
    assert summary['entity_id'] == 'wall'
    assert summary['original_mesh_content_verified'] is summary['alignment_verified'] is False
    assert str(structure_source[0]).encode() not in raw
    result = node_read(raw, args)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == summary


@pytest.mark.parametrize('damage', ['digest', 'magic', 'length', 'index', 'nan', 'trailing',
                                  'binding', 'promote', 'duplicate', 'wrong_element',
                                  'counts', 'noncanonical', 'extra_field'])
def test_corruption_or_wrong_binding_is_rejected(structure_source, damage):
    raw, args = fixture_component(structure_source)
    size = struct.unpack_from('<I', raw, 8)[0]
    header = json.loads(raw[12:12 + size])
    payload = raw[12 + size:]
    if damage == 'digest':
        args['expected_sha256'] = '0' * 64
    elif damage == 'magic':
        raw = b'INVALID!' + raw[8:]
    elif damage == 'length':
        raw = raw[:8] + struct.pack('<I', 4097) + raw[12:]
    elif damage == 'index':
        start = 12 + size + header['vertices'] * 24
        raw = raw[:start] + struct.pack('<I', header['vertices']) + raw[start + 4:]
    elif damage == 'nan':
        raw = raw[:12 + size] + struct.pack('<d', float('nan')) + payload[8:]
    elif damage == 'trailing':
        raw += b'!'
    elif damage == 'wrong_element':
        args['expected_element'] = 'e00002'
    else:
        if damage == 'binding':
            header['structure_sha256'] = '0' * 64
        elif damage == 'promote':
            header['alignment_verified'] = True
        elif damage == 'counts':
            header['vertices'] = 200_001
        elif damage == 'extra_field':
            header['traversable'] = True
        metadata = canonical(header)
        if damage == 'duplicate':
            metadata = b'{"unit":"m",' + metadata[1:]
        elif damage == 'noncanonical':
            metadata = b' ' + metadata
        raw = raw[:8] + struct.pack('<I', len(metadata)) + metadata + payload
    if damage != 'digest':
        args['expected_sha256'] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        inspect_geometry_component(raw, **args)
    result = node_read(raw, args)
    assert result.returncode == 1
    assert not result.stdout


def test_mesh_budget_rejected_before_loading(structure_source, monkeypatch):
    root, catalog = structure_source
    catalog['products'][1]['mesh']['vertices'] = 200_001
    def never(*args):
        pytest.fail('oversize mesh reached loader')
    monkeypatch.setattr('packages.views.agent.ifc_geometry_exchange.load_mesh', never)
    with pytest.raises(ValueError, match='budget'):
        build_geometry_component(root, SPACE, '0' * 64, catalog, 'e00001')


def test_export_authorization_integrity_and_head(ifc_secured, monkeypatch):
    env, access, root, config = ifc_secured
    _, client, _, _, _, _, spaces, *_ = env
    pin = declare(root, config)
    params = dict(space_id=spaces[0]['id'], catalog_sha256=pin, element_id='e00001')
    assert client.get(ROUTE, params=params).status_code == 401
    sign_in(env, 'usr_local_test')
    original = access.scene_ifc.catalog
    def never(*args):
        pytest.fail('unauthorized geometry read reached storage')
    monkeypatch.setattr(access.scene_ifc, 'catalog', never)
    assert client.get(ROUTE, params=params).status_code == 403
    monkeypatch.setattr(access.scene_ifc, 'catalog', original)
    sign_in(env, 'usr_engineer')
    response = client.get(ROUTE, params=params)
    assert response.status_code == 200, response.text
    sha = hashlib.sha256(response.content).hexdigest()
    assert response.headers['x-content-sha256'] == sha
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-disposition'] == f'attachment; filename="ifc-geometry-{sha}.bin"'
    head = client.head(ROUTE, params=params)
    assert head.status_code == 200
    assert not head.content
    assert head.headers['x-content-sha256'] == sha
    for change, status in [({'element_id': '../bad'}, 422), ({'element_id': 'e99999'}, 409),
                           ({'catalog_sha256': 'bad'}, 422), ({'catalog_sha256': '0' * 64}, 409),
                           ({'space_id': spaces[1]['id']}, 403), ({'root': 'private'}, 422)]:
        assert client.get(ROUTE, params=params | change).status_code == status
    assert client.post(ROUTE, json={}).status_code == 403
    mesh = root / 'e00001.npz'
    original_mesh = mesh.read_bytes()
    mesh.write_bytes(b'changed')
    assert client.get(ROUTE, params=params).status_code == 409
    mesh.write_bytes(original_mesh)
    (root / 'source.ifc').write_bytes(b'changed')
    assert client.get(ROUTE, params=params).status_code == 409


def test_schema_matches_contract():
    assert json.loads(Path('contracts/schemas/ifc-element-geometry-v0.1.schema.json').read_text()) == GeometryHeader.model_json_schema()


def test_absent_or_undeclared_geometry_is_rejected(structure_source):
    root, catalog = structure_source
    with pytest.raises(ValueError, match='extracted_declaration'):
        build_geometry_component(root, SPACE, digest(root / 'ifc.json'), catalog, 'e99999')
    catalog['products'][1]['geometry_status'] = 'no_representation'
    with pytest.raises(ValueError, match='extracted_declaration'):
        build_geometry_component(root, SPACE, digest(root / 'ifc.json'), catalog, 'e00001')
