"""Public globe provider configuration; identity and scene access remain in existing gates."""
import json
import os
import re
from urllib.parse import urlsplit


def public_url(value):
    if any(ord(c) < 33 for c in value) or '\\' in value:
        raise ValueError('globe_public_url_invalid')
    if value.startswith('/') and not value.startswith('//') and '\\' not in value and not urlsplit(value).query and not urlsplit(value).fragment:
        return value
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(ord(c) < 33 for c in value) or '\\' in value):
        raise ValueError('globe_public_url_invalid')
    return value


def exact_origin(value):
    if not re.fullmatch(r'https?://[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::[0-9]{1,5})?', value):
        raise ValueError('globe_embed_origin_invalid')
    parsed = urlsplit(value)
    if (parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost')
            or any(ord(c) < 33 for c in value) or '\\' in value):
        raise ValueError('globe_embed_origin_invalid')
    # Accessing port also rejects malformed ports.
    parsed.port
    return value


class GlobeRuntime:
    def __init__(self, imagery_url, terrain_url, embed_origins):
        self.imagery_url = public_url(imagery_url) if imagery_url else None
        self.terrain_url = public_url(terrain_url) if terrain_url else None
        self.embed_origins = tuple(exact_origin(value) for value in embed_origins)

    @classmethod
    def from_env(cls):
        origins = json.loads(os.environ.get('COSPACE_GLOBE_EMBED_ORIGINS', '[]'))
        if not isinstance(origins, list) or len(origins) > 30 or any(not isinstance(value, str) for value in origins):
            raise ValueError('globe_embed_origins_invalid')
        return cls(os.environ.get('COSPACE_GLOBE_IMAGERY_URL', 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'),
                   os.environ.get('COSPACE_GLOBE_TERRAIN_URL', 'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer'), origins)

    def public(self, origin):
        value = {'profile': 'vxture.globe-config/0.1', 'assetsBaseUrl': '/assets/cesium/',
                 'sdkVersion': '0.1.0', 'cesiumVersion': '1.147.0', 'embedOrigins': [origin, *self.embed_origins]}
        if self.imagery_url:
            value['imagery'] = {'url': self.imagery_url, 'maximumLevel': 19,
                                'credit': os.environ.get('COSPACE_GLOBE_IMAGERY_CREDIT', 'Esri, Maxar, Earthstar Geographics, and the GIS User Community')}
        if self.terrain_url:
            value['terrain'] = {'url': self.terrain_url}
        return value

    def allowed_parent(self, parent, origin):
        return parent == origin or parent in self.embed_origins
