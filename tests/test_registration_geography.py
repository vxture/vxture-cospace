from copy import deepcopy
import numpy as np
import pytest

from packages.spatial.registration_geography import enu_to_geographic, geographic_to_enu, validate_binding
from test_scene_registrations import registration, service, source, command, approval


def binding(document):
    document['target'].update(horizontal_reference='WGS84 local ENU', vertical_reference='WGS84 local ENU up')
    return dict(adapter='wgs84_local_enu/1', target_frame_id=document['target']['frame_id'],
                longitude_deg=116.4, latitude_deg=39.9, ellipsoidal_height_m=42.,
                realization='WGS84(G2139)', coordinate_epoch=2026., evidence_ref='survey-origin-record')


@pytest.mark.parametrize('longitude,latitude', [(116.4,39.9), (121.5,31.2), (-73.9,40.7)])
def test_enu_origin_axis_height_and_submillimetre_numeric_roundtrip(registration, longitude, latitude):
    reference=binding(registration)
    reference.update(longitude_deg=longitude, latitude_deg=latitude)
    assert np.allclose(enu_to_geographic([0.,0.,0.],reference),[longitude,latitude,42.],atol=1e-8,rtol=0)
    assert enu_to_geographic([100.,0.,0.],reference)[0] > longitude
    assert enu_to_geographic([0.,100.,0.],reference)[1] > latitude
    assert abs(enu_to_geographic([0.,0.,10.],reference)[2]-52.)<1e-7
    for point in ([1000.,-1500.,12.],[-500.,300.,-9.],[10000.,12000.,100.]):
        assert np.linalg.norm(np.array(geographic_to_enu(enu_to_geographic(point,reference),reference))-point)<1e-6


def test_geographic_datum_scope_and_explicit_configuration(registration,tmp_path):
    reference=binding(registration)
    assert validate_binding(registration,reference)==reference
    wrong=deepcopy(registration)
    wrong['target']['vertical_reference']='orthometric'
    with pytest.raises(ValueError,match='datum_mismatch'):validate_binding(wrong,reference)
    wrong=deepcopy(registration);wrong['matrix'][0][3]=30_000.
    with pytest.raises(ValueError,match='extent_unsupported'):validate_binding(wrong,reference)
    writer=service(tmp_path)
    with pytest.raises(ValueError,match='adapter_not_enabled'):
        writer.change(source(registration),command(registration,geographic_binding=reference))
    writer.adapters={'wgs84_local_enu/1'}
    registration['synthetic']=False
    writer.change(source(registration),command(registration,geographic_binding=reference))
    writer.change(source(registration),command(registration,'submit',1,2))
    reviewer=service(tmp_path,'reviewer')
    reviewer.change(source(registration),command(registration,'approve',2,3,approval=approval(registration)),can_review=True)
    writer.change(source(registration),command(registration,'adopt',3,4))
    assert writer.read(source(registration))['can_focus_geographic_map']
    assert not reviewer.read(source(registration))['can_focus_geographic_map']
    writer.clock=lambda:'2026-11-23T00:00:00Z'
    assert not writer.read(source(registration))['can_focus_geographic_map']


def test_known_equatorial_cartesian_solution_is_independent_of_inverse(registration):
    from math import atan2, degrees, sqrt
    reference=binding(registration)
    reference.update(longitude_deg=0.,latitude_deg=0.,ellipsoidal_height_m=0.)
    result=enu_to_geographic([100.,0.,0.],reference)
    assert abs(result[0]-degrees(atan2(100.,6378137.)))<1e-12
    assert abs(result[1])<1e-12
    assert abs(result[2]-(sqrt(6378137.**2+100.**2)-6378137.))<1e-8
