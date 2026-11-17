import json

import numpy as np
import pytest

from experiments.scripts.ifc_section_regions import propose_regions, report_html
from packages.construction.section_regions import _line_cells, enclosed_section_regions
from packages.data.ifc_inspection import digest
from test_ifc_inspection import assets_at


def section(lines, z=1.):
    return dict(z_m=z, segments=[dict(source_entity_id=f'wall-{i}', ifc_type='IfcWall',
                                     triangle_index=i, points_m=[[a[0], a[1], z], [b[0], b[1], z]])
                                 for i, (a, b) in enumerate(lines)])


def square(size=4., shift=0.):
    a, b = shift, size + shift
    return [([a, a], [b, a]), ([b, a], [b, b]), ([b, b], [a, b]), ([a, b], [a, a])]


def test_closed_void_runs_area_and_provenance_are_reproducible():
    source = section(square())
    result = enclosed_section_regions(source, resolution=.1)
    assert result == enclosed_section_regions(source, resolution=.1)
    assert source == section(square())
    assert len(result['candidates']) == 1
    region = result['candidates'][0]
    assert region['cells'] == 38 * 38
    assert region['raster_area_m2'] == pytest.approx(14.44)
    assert sum(b - a for _, a, b in region['runs']) == region['cells']
    assert region['source_segment_indices'] == [0, 1, 2, 3]
    assert region['source_entity_ids'] == ['wall-0', 'wall-1', 'wall-2', 'wall-3']
    origin = np.asarray(result['origin_xy_m'])
    for row, a, b in region['runs']:
        centers = origin + (np.array([[a, row], [b - 1, row]]) + .5) * .1
        assert np.all(centers > 0) and np.all(centers < 4)


def test_clear_gap_leaks_to_exterior_and_partition_creates_two_voids():
    lines = square()
    lines[0] = ([0, 0], [1.5, 0])
    lines.append(([2.5, 0], [4, 0]))
    assert enclosed_section_regions(section(lines), resolution=.1)['candidates'] == []
    split = enclosed_section_regions(section(square() + [([2, 0], [2, 4])]), resolution=.1)
    assert len(split['candidates']) == 2
    assert all(4 in r['source_segment_indices'] for r in split['candidates'])


def test_door_or_virtual_opening_does_not_close_wall_gap():
    source = section(square())
    for kind in ('IfcDoor', 'IfcOpeningElement', 'IfcSlab', 'IfcStairFlight'):
        source['segments'][0]['ifc_type'] = kind
        result = enclosed_section_regions(source, resolution=.1)
        assert result['candidates'] == []
        assert result['barrier_segment_count'] == 3
    source['segments'].insert(0, dict(source['segments'][0], ifc_type='IfcDoor'))
    source['segments'][1]['ifc_type'] = 'IfcWall'
    result = enclosed_section_regions(source, resolution=.1)
    assert result['candidates'][0]['source_segment_indices'] == [1, 2, 3, 4]


def test_nested_ring_not_filled_and_minimum_area_explicit():
    result = enclosed_section_regions(section(square(6) + square(2, 2)), resolution=.1)
    assert len(result['candidates']) == 2
    run_cells = [{(r, c) for r, a, b in candidate['runs'] for c in range(a, b)}
                 for candidate in result['candidates']]
    assert not run_cells[0] & run_cells[1]
    assert enclosed_section_regions(section(square()), resolution=.1, minimum_area=15)['candidates'] == []


def test_supercover_corner_edge_and_reverse_order():
    origin = np.array([-1., -1.])
    diagonal = _line_cells(np.array([[0., 0.], [2., 2.]]), origin, 1.)
    assert np.array_equal(diagonal, _line_cells(np.array([[2., 2.], [0., 0.]]), origin, 1.))
    cells = set(map(tuple, diagonal))
    assert {(0, 0), (0, 1), (1, 0), (1, 1), (1, 2), (2, 1), (2, 2), (2, 3), (3, 2), (3, 3)} <= cells
    edge = _line_cells(np.array([[0., 0.], [2., 0.]]), origin, 1.)
    assert set(edge[:, 1]) == {0, 1}


def test_subcell_gap_can_close_and_is_not_claimed_as_exact_boundary():
    # Both endpoints land in the same barrier cell. This deliberately documents raster ambiguity.
    lines = square(4, .03)
    lines[0] = ([.03, .03], [1.43, .03])
    lines.append(([1.49, .03], [4.03, .03]))
    assert len(enclosed_section_regions(section(lines), resolution=.1)['candidates']) == 1
    assert enclosed_section_regions(section(lines), resolution=.02)['candidates'] == []


@pytest.mark.parametrize('resolution', [True, 0, .001, 1., float('nan'), float('inf')])
def test_bad_parameters_rejected(resolution):
    with pytest.raises(ValueError, match='parameters'):
        enclosed_section_regions(section([]), resolution=resolution)


@pytest.mark.parametrize('budget', ['MAX_CELLS', 'MAX_STEPS', 'MAX_SEGMENTS', 'MAX_REGIONS', 'MAX_RUNS', 'MAX_REGION_SCAN'])
def test_budgets_refuse_instead_of_truncating(monkeypatch, budget):
    monkeypatch.setattr('packages.construction.section_regions.' + budget, 0)
    with pytest.raises(ValueError, match='budget'):
        enclosed_section_regions(section(square()), resolution=.1)


def test_empty_diagonal_and_degenerate_line_have_no_voids():
    for lines in ([], [([0, 0], [4, 4])], [([0, 0], [0, 0])]):
        assert enclosed_section_regions(section(lines), resolution=.1)['candidates'] == []


def test_invalid_plane_or_coordinates_rejected():
    for xyz in ([0, 0, 2], [float('nan'), 0, 1], [1_000_001, 0, 1]):
        source = section(square())
        source['segments'][0]['points_m'][0] = xyz
        with pytest.raises(ValueError, match='coordinates'):
            enclosed_section_regions(source, resolution=.1)


def test_pinned_source_roundtrip_escaped_html_and_rejects_changed_mesh(tmp_path):
    _, _, root = assets_at(tmp_path, 'space-' + '1' * 16)
    pin = digest(root / 'ifc.json')
    report = propose_regions(root, expected_catalog_sha256=pin, heights=[1.], resolutions=[.1, .2])
    assert report['confirmed_spaces'] == report['confirmed_connections'] == []
    assert report['real_release_ready'] is False
    assert report['ontology_bound'] is False
    assert report['alignment_verified'] is False
    assert report['source_sections_sha256']
    assert json.loads(json.dumps(report)) == report
    report['sections'][0]['segments'][0]['source_entity_id'] = '<img src=x onerror=alert(1)>'
    html = report_html(report)
    assert '<img src=x' not in html
    assert '&lt;img src=x' in html
    (root / 'e00001.npz').write_bytes(b'changed')
    with pytest.raises(ValueError, match='ifc_mesh_changed'):
        propose_regions(root, expected_catalog_sha256=pin, heights=[1.], resolutions=[.1])

