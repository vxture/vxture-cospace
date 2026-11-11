import pytest
from packages.service.globe_runtime import GlobeRuntime, exact_origin, public_url
from test_platform_business import secured, sign_in
from test_platform_login import runtime


@pytest.mark.parametrize('value', ['https://agent.example;script-src', 'https://agent.example/anything',
    'https://user@agent.example', 'https://*.example', 'http://agent.example', 'https://a:99999',
    'https://agent.example\n', 'https://agent.example?x=y', 'https://agent.example"'])
def test_reject_unsafe_origins(value):
    with pytest.raises(ValueError):exact_origin(value)


@pytest.mark.parametrize('value', ['https://user:secret@maps.example/tiles', '//other.example/tiles',
    'https://maps.example/tiles?key=secret', '/tiles\n', 'http://maps.example/tiles'])
def test_public_provider_configuration_contains_no_credentials(value):
    with pytest.raises(ValueError):public_url(value)


def test_runtime_defaults_and_origin_isolation(monkeypatch):
    monkeypatch.setenv('COSPACE_GLOBE_EMBED_ORIGINS', '["https://agent.example"]')
    config=GlobeRuntime.from_env()
    assert config.allowed_parent('https://agent.example','https://cospace.example')
    assert not config.allowed_parent('https://agent.example.evil','https://cospace.example')
    assert config.public('https://cospace.example')['cesiumVersion']=='1.147.0'
    monkeypatch.setenv('COSPACE_GLOBE_IMAGERY_URL','')
    monkeypatch.setenv('COSPACE_GLOBE_TERRAIN_URL','')
    assert 'terrain' not in GlobeRuntime.from_env().public('https://cospace.example')
    monkeypatch.setenv('COSPACE_GLOBE_EMBED_ORIGINS','{"origin":"https://agent.example"}')
    with pytest.raises(ValueError):GlobeRuntime.from_env()


def test_config_requires_session_and_embed_is_exact_origin(secured):
    rp,client,*_=secured
    assert client.get('/api/globe/config').status_code==401
    sign_in(secured)
    response=client.get('/api/globe/config')
    assert response.status_code==200
    assert response.json()['embedOrigins']==[rp.config.origin]
    assert response.headers['cache-control']=='no-store'
    assert client.get('/api/globe/config?token=x').status_code==403
    denied=client.get('/space',params={'embed':'globe','parent_origin':'https://evil.example'})
    assert denied.status_code==403
    own=client.get('/space',params={'embed':'globe','parent_origin':rp.config.origin})
    assert own.headers['content-security-policy']=="frame-ancestors 'self' "+rp.config.origin
    assert client.get('/space?embed=globe&parent_origin='+rp.config.origin+'&parent_origin=https://evil.example').status_code==403
