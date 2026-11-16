import numpy as np
import pytest

from experiments.scripts.ifc_sections import cut_sections, triangle_section
from packages.data.ifc_inspection import digest
from test_ifc_inspection import assets_at
from test_ifc_structure_review import structure_source


@pytest.mark.parametrize('triangle,z,kind', [
    ([[0, 0, -1], [1, 0, 1], [0, 1, 1]], 0, 'segment'),
    ([[0, 0, 0], [1, 0, 0], [0, 1, 1]], 0, 'segment'),
    ([[0, 0, 0], [1, 0, 1], [0, 1, 1]], 0, 'touch'),
    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], 0, 'coplanar'),
    ([[0, 0, 1], [1, 0, 1], [0, 1, 1]], 0, 'none'),
])
def test_triangle_intersections(triangle, z, kind):
    actual, segment = triangle_section(np.asarray(triangle, dtype=float), z)
    assert actual == kind
    if kind == 'segment':
        assert len(segment) == 2
        assert all(point[2] == z for point in segment)
        assert segment[0] != segment[1]
    else:
        assert segment is None


def test_source_segment_indices_and_coordinates(tmp_path):
    _, _, root = assets_at(tmp_path, 'space-' + '1' * 16)
    report = cut_sections(root, expected_catalog_sha256=digest(root / 'ifc.json'), heights=[1.])
    segments = report['sections'][0]['segments']
    assert len(segments) == 3
    assert {row['triangle_index'] for row in segments} == {1, 2, 3}
    assert all(row['source_entity_id'] == 'wall' for row in segments)
    assert all(point[2] == 1 for row in segments for point in row['points_m'])
    assert report['confirmed_spaces'] == []
    assert report['alignment_verified'] is False
    (root / 'e00001.npz').write_bytes(b'changed')
    with pytest.raises(ValueError, match='ifc_mesh_changed'):
        cut_sections(root, expected_catalog_sha256=digest(root / 'ifc.json'), heights=[1.])


@pytest.mark.parametrize('heights', [[], [1, 1], [float('nan')], [float('inf')], [True], list(range(9))])
def test_invalid_heights_rejected(heights, tmp_path):
    with pytest.raises(ValueError, match='ifc_section_heights'):
        cut_sections(tmp_path, expected_catalog_sha256='0' * 64, heights=heights)


def test_changed_catalog_rejected(tmp_path):
    _, _, root = assets_at(tmp_path, 'space-' + '1' * 16)
    with pytest.raises(ValueError, match='ifc_section_catalog_digest'):
        cut_sections(root, expected_catalog_sha256='0' * 64, heights=[1.])


def test_editor_seeds_pinned_empty_annotations(structure_source):
    import json
    from experiments.scripts.ifc_annotation_editor import editor_html
    root, _ = structure_source
    html = editor_html(root, expected_catalog_sha256=digest(root / 'ifc.json'), heights=[1.])
    encoded = html.split('<script type="application/json" id="editor-data">', 1)[1].split('</script>', 1)[0]
    data = json.loads(encoded)
    assert data['worksheet']['areas'] == []
    assert data['worksheet']['assessment'] == 'unverified'
    assert len(data['worksheet']['connections']) == 2
    assert data['views'][0]['z'] == 1.
    assert data['views'][0]['scale'] > 0
    assert data['section_sha256']
    assert all(not row['endpoints'] for row in data['worksheet']['connections'])
