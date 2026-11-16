import numpy as np
import pytest

from packages.construction.ifc_registration_proposal import registration_proposals
from packages.construction.rgbd_tracking import transform


def test_recovers_known_rigid_geometry_without_claiming_verification():
    source = np.random.default_rng(31).normal(size=(150, 3)) * [3, 1, .3]
    matrix = np.array([[.6, -.8, 0, 4], [.8, .6, 0, -2], [0, 0, 1, 1], [0, 0, 0, 1]])
    report = registration_proposals(source, transform(source, matrix))
    assert len(report['candidates']) == 24
    best = report['candidates'][0]
    assert best['trimmed_rmse'] < 1e-10
    assert np.allclose(best['ifc_to_cloud_numeric'], matrix)
    assert report['alignment_verified'] is report['unit_verified'] is report['real_release_ready'] is False
    assert report['independent_control_count'] == 0


@pytest.mark.parametrize('points', [np.zeros((12, 3)), np.zeros((11, 3)), np.zeros((6001, 3)),
                                  np.full((12, 3), np.nan), np.ones((12, 2))])
def test_invalid_geometry_and_budgets_rejected(points):
    with pytest.raises(ValueError, match='proposal_'):
        registration_proposals(points, np.random.default_rng(1).normal(size=(15, 3)))
