"""Canonical public entry, legacy navigation and assets without broad SPA fallback."""
import pytest
from fastapi.testclient import TestClient
from packages.service.platform_auth_http import create_auth_app
from packages.infrastructure.platform_rp import safe_return
from test_platform_login import runtime, begin


def test_root_serves_application_and_only_assets_are_public(runtime,tmp_path):
    rp,_,_,_=runtime
    front=tmp_path/'front';front.mkdir()
    (front/'layout.html').write_text('<html>CoSpace entry</html>')
    (front/'private.html').write_text('not a public document')
    (front/'assets').mkdir();(front/'assets'/'app.js').write_text('export {}')
    with TestClient(create_auth_app(rp,front),base_url=rp.config.origin,follow_redirects=False) as client:
        response=client.get('/')
        assert response.status_code==200 and response.text=='<html>CoSpace entry</html>'
        assert response.headers['content-type'].startswith('text/html')
        assert response.headers['cache-control']=='no-store'
        assert client.head('/').status_code==200
        assert client.get('/workbench/assets/app.js').text=='export {}'
        assert client.get('/workbench/private.html').status_code==404
        assert client.get('/unknown').status_code==404
        for path in ('/workbench','/workbench/','/workbench/layout.html','/workbench/index.html'):
            old=client.get(path+'?screen=space&preview=1')
            assert old.status_code==308 and old.headers['location']=='/?screen=space&preview=1'


@pytest.mark.parametrize('target',['/','/?screen=space#space?space=test','/#build',
    '/workbench/layout.html?screen=space#space','/workbench/index.html#data'])
def test_login_accepts_canonical_and_normalizes_old_bookmarks(runtime,target):
    rp,client,accounts,_=runtime
    q,code=begin(rp,client,accounts,returnTo=target)
    response=client.get('/auth/callback',params={'state':q['state'],'code':code})
    expected=target.replace('/workbench/layout.html','/').replace('/workbench/index.html','/')
    assert response.headers['location']==rp.config.origin+expected


@pytest.mark.parametrize('target',['/auth/logout','//evil.example','/%2f%2fevil.example',
    '/%5cevil.example','/%0d%0aLocation:evil','/api/spaces','/workbench/../auth/login'])
def test_root_support_does_not_expand_redirect_authority(target):
    with pytest.raises(ValueError):safe_return(target)


def test_missing_entry_does_not_redirect_in_a_loop(runtime):
    _,client,_,_=runtime
    response=client.get('/')
    assert response.status_code==404 and 'location' not in response.headers
