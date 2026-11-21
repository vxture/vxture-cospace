"""Versioned WGS84 local-ENU adapter. No datum shifts or basemap offsets."""
from math import atan2, cos, degrees, hypot, radians, sin, sqrt
from typing import Annotated, Literal

import numpy as np
from pydantic import Field
from packages.spatial.georeference import Fixed, Text, Point, RegistrationInput

ADAPTER = 'wgs84_local_enu/1'
A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)
MAX_RADIUS_M = 20_000


class GeographicBinding(Fixed):
    adapter: Literal['wgs84_local_enu/1']
    target_frame_id: Text
    longitude_deg: Annotated[float, Field(ge=-180, le=180)]
    latitude_deg: Annotated[float, Field(gt=-89, lt=89)]
    ellipsoidal_height_m: Annotated[float, Field(ge=-12000, le=100000)]
    realization: Literal['WGS84(G1762)', 'WGS84(G2139)', 'WGS84(G2296)']
    coordinate_epoch: Annotated[float, Field(ge=1984, le=2100)]
    evidence_ref: Text


def validate_binding(document, binding):
    if binding is None:
        return None
    request = RegistrationInput.model_validate(document)
    value = GeographicBinding.model_validate(binding)
    if (request.target.kind != 'engineering' or value.target_frame_id != request.target.frame_id
            or request.target.horizontal_reference != 'WGS84 local ENU'
            or request.target.vertical_reference != 'WGS84 local ENU up'):
        raise ValueError('registration_geographic_datum_mismatch')
    # The route is a surveyed tangent frame with a bounded local extent. A scene
    # entrance longitude or an EPSG string alone is never accepted as an origin.
    lower, upper = request.source.bounds_m
    corners = np.array([[x, y, z, 1.] for x in (lower[0], upper[0])
                        for y in (lower[1], upper[1]) for z in (lower[2], upper[2])])
    target = corners @ np.asarray(request.matrix).T
    if np.any(np.linalg.norm(target[:, :3], axis=1) > MAX_RADIUS_M):
        raise ValueError('registration_geographic_extent_unsupported')
    return value.model_dump()


def basis(binding):
    lon, lat = radians(binding.longitude_deg), radians(binding.latitude_deg)
    slon, clon, slat, clat = sin(lon), cos(lon), sin(lat), cos(lat)
    n = A / sqrt(1 - E2 * slat**2)
    h = binding.ellipsoidal_height_m
    origin = np.array([(n+h)*clat*clon, (n+h)*clat*slon, (n*(1-E2)+h)*slat])
    rotation = np.array([[-slon, -slat*clon, clat*clon],
                         [clon, -slat*slon, clat*slon], [0., clat, slat]])
    return origin, rotation


def enu_to_geographic(point, binding):
    value = GeographicBinding.model_validate(binding)
    point = np.asarray(point, dtype=np.float64)
    if point.shape != (3,) or not np.isfinite(point).all() or np.linalg.norm(point) > MAX_RADIUS_M:
        raise ValueError('registration_geographic_extent_unsupported')
    origin, rotation = basis(value)
    x, y, z = origin + rotation @ point
    p = hypot(x, y)
    latitude = atan2(z, p*(1-E2))
    for _ in range(12):
        n = A / sqrt(1-E2*sin(latitude)**2)
        latitude = atan2(z + E2*n*sin(latitude), p)
    n = A / sqrt(1-E2*sin(latitude)**2)
    height = p/cos(latitude)-n
    return [degrees(atan2(y, x)), degrees(latitude), float(height)]


def geographic_to_enu(point, binding):
    value = GeographicBinding.model_validate(binding)
    lon, lat, height = point
    if not all(np.isfinite([lon, lat, height])) or abs(lon) > 180 or abs(lat) > 90:
        raise ValueError('registration_invalid_geographic_point')
    lon, lat = radians(lon), radians(lat)
    n = A / sqrt(1-E2*sin(lat)**2)
    ecef = np.array([(n+height)*cos(lat)*cos(lon), (n+height)*cos(lat)*sin(lon),
                     (n*(1-E2)+height)*sin(lat)])
    origin, rotation = basis(value)
    result = rotation.T @ (ecef-origin)
    if np.linalg.norm(result) > MAX_RADIUS_M:
        raise ValueError('registration_geographic_extent_unsupported')
    return result.tolist()


def project_objects(document, binding, bounds_m, objects):
    validate_binding(document, binding)
    matrix = np.asarray(document['matrix'])
    result = []
    for obj in objects:
        source = obj['anchor_m']
        row = {'object_id': obj['object_id'], 'name': obj['properties'].get('name', obj['object_id'])}
        if not all(bounds_m[0][i] <= source[i] <= bounds_m[1][i] for i in range(3)):
            result.append({**row, 'available': False, 'reason': 'outside_approved_extent'})
            continue
        target = (matrix @ np.array([*source, 1.]))[:3].tolist()
        location = enu_to_geographic(target, binding)
        result.append({**row, 'available': True, 'source_m': source, 'target_m': target,
                       'longitude_deg': location[0], 'latitude_deg': location[1],
                       'ellipsoidal_height_m': location[2]})
    return result
