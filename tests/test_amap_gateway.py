import httpx2 as httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from packages.service.amap_gateway import AmapGateway
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def client(gateway):
    app=FastAPI()
    @app.get('/{remaining:path}')
    async def dispatch(request:Request,remaining:str):return await gateway.dispatch(request)
    return TestClient(app)


def test_map_requires_authenticated_business_session(secured):
    _,c,*_=secured
    assert c.get('/api/map/config').status_code==401
    assert c.get('/_AMapService/v4/map/styles').status_code==401
    sign_in(secured)
    assert c.get('/api/map/config').json()=={'enabled':False,'provider':'amap'}
    assert c.get('/_AMapService/v4/map/styles').status_code==503


def test_proxy_injects_server_secret_only_for_allowlisted_upstream():
    key='a'*32;secret='b'*32;calls=[]
    def upstream(request):
        calls.append(request)
        return httpx.Response(200,content=b'{"style":"darkblue"}',headers={'Content-Type':'application/json','Set-Cookie':'unexpected=1'})
    c=client(AmapGateway(key,secret,httpx.MockTransport(upstream)))
    config=c.get('/api/map/config');assert config.json()['key']==key and secret not in config.text
    response=c.get('/_AMapService/v4/map/styles',params={'key':key,'style':'darkblue'})
    assert response.status_code==200 and 'set-cookie' not in response.headers
    assert str(calls[0].url).startswith('https://webapi.amap.com/v4/map/styles?')
    assert calls[0].url.params['jscode']==secret
    for path in ('/_AMapService/v3/place/text','/_AMapService/https://evil.example','/_AMapService/v4/map/styles?jscode=override',
                 '/_AMapService/v4/map/styles?key=wrong','/_AMapService/v4/map/styles?callback=a&callback=b'):
        assert c.get(path).status_code==403
    assert c.get('/_AMapService/v4/map/styles',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert len(calls)==1


@pytest.mark.parametrize('status,content',[(302,b''),(500,b'failed'),(200,('b'*32).encode()),(200,b'x'*(8*1024*1024+1))],ids=['redirect','server-error','secret-echo','over-budget'])
def test_proxy_bounds_upstream_and_hides_diagnostics(status,content):
    c=client(AmapGateway('a'*32,'b'*32,httpx.MockTransport(lambda _:httpx.Response(status,content=content))))
    response=c.get('/_AMapService/v4/map/styles')
    assert response.status_code==502 and 'b'*32 not in response.text


def test_configuration_rejects_partial_invalid_values(monkeypatch):
    monkeypatch.setenv('COSPACE_AMAP_WEB_KEY','invalid')
    with pytest.raises(ValueError,match='amap_configuration_invalid'):AmapGateway.from_env()


def test_place_search_uses_fixed_query_and_bounded_results():
    calls=[]
    def upstream(request):
        calls.append(request.url)
        return httpx.Response(200,json={'status':'1','pois':[{'name':'故宫','location':'116.397,39.918'}]})
    c=client(AmapGateway('a'*32,'b'*32,httpx.MockTransport(upstream)))
    path='/_AMapService/place-search'
    for params in ({},{'keywords':'x'},{'keywords':'x'*81},{'keywords':'故宫','offset':100}):
        assert c.get(path,params=params).status_code==422
    assert c.get(path,params={'keywords':'故宫'},headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    result=c.get(path,params={'keywords':'故宫'})
    assert result.status_code==200 and result.json()['pois'][0]['name']=='故宫'
    assert len(calls)==1 and calls[0].host=='restapi.amap.com' and calls[0].path=='/v3/place/text'
    assert calls[0].params['offset']=='8' and calls[0].params['keywords']=='故宫'
