"""Canonical public entry, legacy navigation and assets without broad SPA fallback."""
import pytest
from fastapi.testclient import TestClient
from packages.service.platform_auth_http import create_auth_app
from packages.infrastructure.platform_rp import safe_return
from packages.infrastructure.platform_rp import APP_ROUTES
from test_platform_login import runtime, begin


def test_root_serves_application_and_only_assets_are_public(runtime,tmp_path):
    rp,_,_,_=runtime
    front=tmp_path/'front';front.mkdir()
    (front/'index.html').write_text('<html>CoSpace entry</html>')
    (front/'private.html').write_text('not a public document')
    (front/'assets').mkdir();(front/'assets'/'app.js').write_text('export {}')
    with TestClient(create_auth_app(rp,front),base_url=rp.config.origin,follow_redirects=False) as client:
        response=client.get('/')
        assert response.status_code==200 and response.text=='<html>CoSpace entry</html>'
        assert response.headers['content-type'].startswith('text/html')
        assert response.headers['cache-control']=='no-store'
        assert client.head('/').status_code==200
        assert client.get('/assets/app.js').text=='export {}'
        assert client.get('/workbench/private.html').status_code==404
        assert client.get('/unknown').status_code==404
        for path in APP_ROUTES:
            direct=client.get(path+'?space=scene-a&tab=flow')
            assert direct.status_code==200 and direct.text==response.text
            assert 'location' not in direct.headers
        for path in ('/index.html','/workbench','/workbench/','/workbench/layout.html','/workbench/index.html'):
            old=client.get(path+'?screen=space&preview=1')
            assert old.status_code==404 and 'location' not in old.headers


@pytest.mark.parametrize('target',['/','/space?space=test','/build?space=test&tab=flow','/data'])
def test_login_returns_directly_to_app_route(runtime,target):
    rp,client,accounts,_=runtime
    q,code=begin(rp,client,accounts,returnTo=target)
    response=client.get('/auth/callback',params={'state':q['state'],'code':code})
    assert response.headers['location']==rp.config.origin+target


@pytest.mark.parametrize('target',['/auth/logout','//evil.example','/%2f%2fevil.example',
    '/%5cevil.example','/%0d%0aLocation:evil','/api/spaces','/workbench/../auth/login',
    '/workbench/layout.html','/index.html','/not-a-route'])
def test_root_support_does_not_expand_redirect_authority(target):
    with pytest.raises(ValueError):safe_return(target)


def test_missing_entry_does_not_redirect_in_a_loop(runtime):
    _,client,_,_=runtime
    response=client.get('/')
    assert response.status_code==404 and 'location' not in response.headers
