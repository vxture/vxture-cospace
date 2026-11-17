import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from packages.data.ifc_inspection import digest
from packages.spatial.scene_identity import canonical
from packages.views.agent.ifc_structure_exchange import (
    build_structure_snapshot, export_structure_snapshot, inspect_structure_snapshot, snapshot_summary,
)
from test_ifc_structure_review import structure_source
from test_ifc_workspace import ifc_secured
from test_ifc_structure_http import declare
from test_platform_business import secured, sign_in
from test_platform_login import runtime

ROUTE = '/api/scene-ifc/structure-snapshot'
SPACE = 'space-' + '1' * 16


def snapshot(env):
    root, doc = env
    return build_structure_snapshot(SPACE, digest(root / 'ifc.json'), doc)


def inspect(raw):
    return inspect_structure_snapshot(raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
                                      expected_source=json.loads(raw)['source'])


def test_deterministic_metadata_preserves_declarations_and_explicit_limits(structure_source):
    raw = snapshot(structure_source)
    assert snapshot(structure_source) == raw
    value = inspect(raw)
    summary = snapshot_summary(value)
    assert summary['entities'] == 6
    assert summary['relations'] == 3
    assert summary['declared_role_counts']['door'] == 1
    assert summary['original_ifc_content_verified'] is False
    assert summary['geometry_included'] is summary['alignment_verified'] is summary['real_release_ready'] is False
    assert b'source.ifc' not in raw
    assert str(structure_source[0]).encode() not in raw
    assert value.source.catalog_sha256 == digest(structure_source[0] / 'ifc.json')
    assert value.source.ifc_sha256 == structure_source[1]['source']['sha256']


@pytest.mark.parametrize('change', [
    lambda d: d.update(real_release_ready=True),
    lambda d: d.update(ontology_bound=True),
    lambda d: d.update(alignment_verified=True),
    lambda d: d.update(geometry_included=True),
    lambda d: d.update(data_kind='real'),
    lambda d: d.update(frame_id='ifc_world_' + '0' * 16),
    lambda d: d.update(confirmed_connections=[]),
    lambda d: d['relations'][0].update(target_id='missing'),
    lambda d: d['entities'].append(d['entities'][0]),
    lambda d: d['entities'][0].update(element_id='../mesh'),
    lambda d: d['entities'][0].update(source_role='traversable'),
])
def test_rejects_broken_references_or_elevated_claims(structure_source, change):
    doc = json.loads(snapshot(structure_source))
    change(doc)
    raw = canonical(doc)
    with pytest.raises(ValueError):
        inspect(raw)


def test_independent_pins_and_json_ambiguity(structure_source):
    raw = snapshot(structure_source)
    source, sha = json.loads(raw)['source'], hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match='byte_digest'):
        inspect_structure_snapshot(raw + b' ', expected_sha256=sha, expected_source=source)
    with pytest.raises(ValueError, match='source_binding'):
        inspect_structure_snapshot(raw, expected_sha256=sha, expected_source=source | {'space_id': 'space-' + '2' * 16})
    ambiguous = b'{"profile":"wrong",' + raw[1:]
    ambiguous_sha = hashlib.sha256(ambiguous).hexdigest()
    with pytest.raises(ValueError, match='duplicate_json_key'):
        inspect_structure_snapshot(ambiguous, expected_sha256=ambiguous_sha, expected_source=source)
    noncanonical = raw + b' '
    with pytest.raises(ValueError, match='canonical_bytes_required'):
        inspect(noncanonical)


def test_export_rechecks_original_catalog_and_source_before_serializing(ifc_secured, monkeypatch):
    env, access, root, config = ifc_secured
    _, _, _, _, _, _, spaces, *_ = env
    pin = declare(root, config)
    def no_mesh(*args):
        pytest.fail('metadata export loaded geometry')
    monkeypatch.setattr('packages.data.ifc_workspace.load_mesh', no_mesh)
    raw = export_structure_snapshot(access.scene_ifc, spaces[0]['id'], pin)
    assert inspect(raw).source.space_id == spaces[0]['id']
    (root / 'source.ifc').write_bytes(b'changed')
    with pytest.raises(ValueError, match='source_changed'):
        export_structure_snapshot(access.scene_ifc, spaces[0]['id'], pin)


def test_http_export_is_authorized_pinned_and_read_only(ifc_secured, monkeypatch):
    env, access, root, config = ifc_secured
    _, client, _, _, _, _, spaces, *_ = env
    pin = declare(root, config)
    params = {'space_id': spaces[0]['id'], 'catalog_sha256': pin}
    assert client.get(ROUTE, params=params).status_code == 401
    original = access.scene_ifc.catalog
    def no_read(*args):
        pytest.fail('unauthorized export reached storage')
    monkeypatch.setattr(access.scene_ifc, 'catalog', no_read)
    sign_in(env, 'usr_local_test')
    assert client.get(ROUTE, params=params).status_code == 403
    sign_in(env, 'usr_engineer')
    monkeypatch.setattr(access.scene_ifc, 'catalog', original)
    result = client.get(ROUTE, params=params)
    assert result.status_code == 200, result.text
    sha = hashlib.sha256(result.content).hexdigest()
    assert result.headers['x-content-sha256'] == sha
    assert result.headers['content-disposition'] == f'attachment; filename="ifc-structure-{sha}.json"'
    assert result.headers['cache-control'] == 'no-store'
    assert result.content == client.get(ROUTE, params=params).content
    assert inspect(result.content).source.catalog_sha256 == pin
    for change, status in [({'space_id': spaces[1]['id']}, 403), ({'catalog_sha256': '0' * 64}, 409),
                           ({'catalog_sha256': 'bad'}, 422), ({'root': 'private'}, 422)]:
        assert client.get(ROUTE, params=params | change).status_code == status
    assert client.post(ROUTE, json={}).status_code == 403
    head = client.head(ROUTE, params=params)
    assert head.status_code == 200
    assert head.headers['x-content-sha256'] == sha
    assert not head.content
    (root / 'source.ifc').write_bytes(b'changed')
    assert client.get(ROUTE, params=params).status_code == 409


def test_legacy_catalog_without_structure_is_not_exported(ifc_secured):
    env, _, root, _ = ifc_secured
    _, client, _, _, _, _, spaces, *_ = env
    sign_in(env, 'usr_engineer')
    response = client.get(ROUTE, params={'space_id': spaces[0]['id'], 'catalog_sha256': digest(root / 'ifc.json')})
    assert response.status_code == 409


def node_read(root, raw, expected_source):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime unavailable')
    path, pin = root / 'snapshot.json', root / 'trusted-source.json'
    path.write_bytes(raw)
    pin.write_bytes(canonical(expected_source))
    script = Path('examples/scene-graph/consumers/read-ifc-structure.mjs').resolve()
    return subprocess.run([str(Path(node).resolve()), '--', str(script), path.name,
                           hashlib.sha256(raw).hexdigest(), pin.name], cwd=root,
                          capture_output=True, text=True, timeout=15, check=False, shell=False)


def test_python_and_independent_node_consumer_agree(structure_source, tmp_path):
    raw = snapshot(structure_source)
    source = json.loads(raw)['source']
    result = node_read(tmp_path, raw, source)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == snapshot_summary(inspect(raw))


@pytest.mark.parametrize('corruption', ['pin', 'reference', 'duplicate_key', 'promote', 'noncanonical'])
def test_independent_consumer_rejects_corrupt_or_ambiguous_input(structure_source, tmp_path, corruption):
    raw = snapshot(structure_source)
    source, doc = json.loads(raw)['source'], json.loads(raw)
    if corruption == 'pin':
        source['catalog_sha256'] = '0' * 64
    elif corruption == 'reference':
        doc['relations'][0]['target_id'] = 'missing'
        raw = canonical(doc)
    elif corruption == 'duplicate_key':
        raw = b'{"profile":"wrong",' + raw[1:]
    elif corruption == 'promote':
        doc['real_release_ready'] = True
        raw = canonical(doc)
    else:
        raw += b' '
    result = node_read(tmp_path, raw, source)
    assert result.returncode == 1
    assert not result.stdout


def test_json_schema_matches_runtime_contract():
    from packages.views.agent.ifc_structure_exchange import StructureSnapshot
    document = json.loads(Path('contracts/schemas/ifc-structure-snapshot-v0.1.schema.json').read_text(encoding='utf-8'))
    assert document == StructureSnapshot.model_json_schema()


@pytest.mark.parametrize('escape', ['parent', 'absolute', 'symlink'])
def test_node_cli_rejects_files_outside_working_directory(tmp_path, escape):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime unavailable')
    root = tmp_path / 'trusted'
    root.mkdir()
    outside = tmp_path / 'outside.json'
    outside.write_text('{}', encoding='utf-8')
    if escape == 'symlink':
        link = root / 'linked.json'
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip('Creating symlinks requires local permission')
        name = link.name
    else:
        name = '../outside.json' if escape == 'parent' else str(outside.resolve())
    script = Path('examples/scene-graph/consumers/read-ifc-structure.mjs').resolve()
    result = subprocess.run([str(Path(node).resolve()), '--', str(script), name,
                             '0' * 64, name], cwd=root, capture_output=True,
                            text=True, timeout=15, check=False, shell=False)
    assert result.returncode == 1
    assert not result.stdout
    expected = 'file_outside_working_directory' if escape == 'symlink' else 'plain_json_filename_required'
    assert expected in result.stderr
