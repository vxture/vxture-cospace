from copy import deepcopy
from itertools import permutations

import numpy as np
import pytest

from packages.spatial.coordinate_axes import registration_readiness, valid_axis_label


@pytest.mark.parametrize('axes,expected', [
    (['Right', 'FORWARD', 'Up'], ['right', 'forward', 'up']),
    (['右', '前', '上'], ['right', 'forward', 'up']),
    (['E', 'N', 'U'], ['east', 'north', 'up']),
    (['N', 'E', 'D'], ['north', 'east', 'down']),
    (['front', 'LEFT', 'up'], ['forward', 'left', 'up']),
    (['forward', 'right', 'down'], ['forward', 'right', 'down']),
    (['X(right)', 'Y_down', 'Z-forward'], ['right', 'down', 'forward']),
    (['X轴东', 'Y轴北', 'Z轴上'], ['east', 'north', 'up']),
])
def test_explicit_aliases_preserve_original_labels(axes, expected):
    before = deepcopy(axes)
    result = registration_readiness(axes)
    assert result['status'] == 'ready'
    assert result['resolved_axes'] == expected and result['axes'] == before and axes == before
    assert not result['coordinate_transform_applied']


@pytest.mark.parametrize('axes,status', [
    (['x', 'y', 'z'], 'needs_declaration'),
    (['sensor_x', 'sensor_y', 'sensor_z'], 'needs_declaration'),
    (['source_x', 'source_y', 'source_z'], 'needs_declaration'),
    (['Y(right)', 'Y(forward)', 'Z(up)'], 'needs_declaration'),
    (['right', 'forward', 'down'], 'left_handed'),
    (['right', 'east', 'up'], 'invalid_axes'),
    (['right', 'north', 'up'], 'invalid_axes'),
    (['east', 'forward', 'up'], 'invalid_axes'),
    (['right', 'up'], 'needs_declaration'),
    ('ENU', 'needs_declaration'),
    ([{}, 'up', 'front'], 'needs_declaration'),
])
def test_ambiguous_invalid_and_left_handed_frames_are_not_guessed(axes, status):
    assert registration_readiness(axes)['status'] == status
    assert registration_readiness(['right', 'forward', 'up'], 'cm')['status'] == 'unsupported_unit'


def test_axis_orientation_matches_independent_determinants():
    vectors = {'right': [1, 0, 0], 'forward': [0, 1, 0], 'up': [0, 0, 1]}
    for axes in permutations(vectors):
        determinant = np.linalg.det([vectors[axis] for axis in axes])
        assert registration_readiness(axes)['status'] == ('ready' if determinant > 0 else 'left_handed')


@pytest.mark.parametrize('value', ['a\nb', '../right', 'r<script>', 'a'*41, ' right', 1])
def test_direction_labels_reject_control_characters_paths_and_unbounded_text(value):
    assert not valid_axis_label(value)
