import numpy as np
import pytest

from packages.construction.registration_sampling import sample_cloud_voxels, sample_triangle_surface
from packages.construction.rgbd_tracking import transform
from experiments.scripts.propose_ifc_registration import surface_triangles
from test_ifc_structure_review import structure_source


def test_surface_samples_follow_area_and_preserve_triangle_membership():
    triangles = np.array([[[0, 0, 0], [2, 0, 0], [0, 1, 0]],
                          [[10, 0, 0], [16, 0, 0], [10, 3, 0]]], dtype=float)
    result = sample_triangle_surface(triangles, count=1000)
    assert result.shape == (1000, 3)
    assert np.count_nonzero(result[:, 0] < 5) == 100
    assert np.all(result[:100, 0] / 2 + result[:100, 1] <= 1 + 1e-12)
    assert np.all((result[100:, 0] - 10) / 6 + result[100:, 1] / 3 <= 1 + 1e-12)
    assert np.allclose(result[100:].mean(0), triangles[1].mean(0), atol=.02)
    assert np.array_equal(result, sample_triangle_surface(triangles, count=1000))
    matrix = np.array([[0, -1, 0, 5], [1, 0, 0, 6], [0, 0, 1, -1], [0, 0, 0, 1]])
    moved = transform(triangles.reshape(-1, 3), matrix).reshape(-1, 3, 3)
    assert np.allclose(sample_triangle_surface(moved, count=1000), transform(result, matrix))


def test_zero_area_faces_do_not_receive_samples():
    result = sample_triangle_surface([[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                                      [[100, 0, 0], [100, 0, 0], [100, 0, 0]]], count=12)
    assert len(result) == 12
    assert result[:, 0].max() <= 1


def test_voxel_sample_is_bounded_deterministic_and_has_only_actual_input_points():
    unique = np.random.default_rng(42).uniform(-10, 10, (2000, 3))
    dense = np.concatenate([unique, np.repeat(unique[:50], 100, axis=0)])
    result, facts = sample_cloud_voxels(dense, maximum=200)
    shuffled, _ = sample_cloud_voxels(dense[::-1], maximum=200)
    assert 12 <= len(result) <= 200
    assert np.array_equal(result, shuffled)
    assert {tuple(row) for row in result}.issubset({tuple(row) for row in unique})
    assert facts['unique_points'] == 2000
    assert facts['voxel_width_numeric'] > 0


@pytest.mark.parametrize('value', [np.zeros((0, 3, 3)), np.zeros((12, 3, 3)),
                                  np.full((12, 3, 3), np.nan), np.zeros((12, 3))])
def test_invalid_surfaces_rejected(value):
    with pytest.raises(ValueError, match='surface_'):
        sample_triangle_surface(value)


@pytest.mark.parametrize('value', [np.zeros((0, 3)), np.full((12, 3), np.inf), np.zeros((12, 2))])
def test_invalid_clouds_rejected(value):
    with pytest.raises(ValueError, match='voxel_'):
        sample_cloud_voxels(value)


def test_structure_loader_uses_source_role_for_ifc_subclasses(structure_source):
    root, catalog = structure_source
    catalog['products'][1]['ifc_type'] = 'IfcWallStandardCase'
    catalog['structure']['entities'][1]['ifc_type'] = 'IfcWallStandardCase'
    result = surface_triangles(root, catalog)
    assert result.shape == (4, 3, 3)


def test_structure_budget_rejected_before_loading_mesh(structure_source, monkeypatch):
    root, catalog = structure_source
    catalog['products'][1]['mesh']['triangles'] = 200001
    def no_mesh(*args):
        pytest.fail('oversized structure loaded mesh')
    monkeypatch.setattr('experiments.scripts.propose_ifc_registration.load_mesh', no_mesh)
    with pytest.raises(ValueError, match='surface_structure_triangle_budget'):
        surface_triangles(root, catalog)


def test_surface_sampling_requires_explicit_structure_source(structure_source):
    root, catalog = structure_source
    catalog.pop('structure')
    with pytest.raises(ValueError, match='source_required'):
        surface_triangles(root, catalog)
