import pytest

from experiments.scripts.ifc_control_review import compare_sources
from experiments.scripts.ifc_control_picker import picker_data
from packages.data.ifc_inspection import digest
from test_ifc_inspection import assets_at
from test_preview_pointcloud import specimen


@pytest.fixture
def sources(tmp_path):
    _, _, ifc = assets_at(tmp_path / 'ifc', 'space-' + '1' * 16)
    cloud = specimen(tmp_path)
    return ifc, cloud, dict(expected_ifc_sha256=digest(ifc / 'ifc.json'),
                            expected_cloud_sha256=digest(cloud / 'cloud.ply'))


def test_comparison_leaves_controls_unverified(sources):
    ifc, cloud, pins = sources
    _, report = compare_sources(ifc, cloud, **pins)
    assert report['status'] == 'not_aligned'
    assert report['alignment_verified'] is report['cloud_unit_verified'] is False
    assert report['pairs'] == []
    assert report['ifc']['artifact_sha256'] == pins['expected_ifc_sha256']
    assert report['cloud']['artifact_sha256'] == pins['expected_cloud_sha256']


@pytest.mark.parametrize('source', ['ifc', 'cloud'])
def test_wrong_source_pin_rejected(sources, source):
    ifc, cloud, pins = sources
    pins[f'expected_{source}_sha256'] = '0' * 64
    with pytest.raises(ValueError, match=f'^comparison_{source}_digest$'):
        compare_sources(ifc, cloud, **pins)


def test_original_ifc_tampering_rejected(sources):
    ifc, cloud, pins = sources
    (ifc / 'source.ifc').write_bytes(b'changed')
    with pytest.raises(ValueError, match='^ifc_source_changed$'):
        compare_sources(ifc, cloud, **pins)


def test_picker_preserves_native_coordinates_and_traceable_indices(sources, monkeypatch):
    ifc, cloud, pins = sources
    monkeypatch.setattr('experiments.scripts.ifc_control_picker.POINT_BUDGET', 1)
    result = picker_data(ifc, cloud, **pins)
    assert result['ifc']['elements'] == [{'start': 0, 'global_id': 'wall', 'ifc_type': 'IfcWall'}]
    assert result['ifc']['vertices'][3] == [0, 0, 4]
    assert result['cloud'] == {'vertices': [[1, 2, .5]], 'stride': 2, 'total': 2}
    assert result['worksheet']['pairs'] == []
    assert result['worksheet']['cloud_unit_verified'] is False
