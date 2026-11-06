"""No credentials or external calls in the container liveness check."""
import json
from urllib.request import Request,build_opener,ProxyHandler

with build_opener(ProxyHandler({})).open(Request('http://127.0.0.1:8088/api/auth/config',
        headers={'Host':'cospace.ruyin.work'}),timeout=3) as response:
    value=json.loads(response.read(4096))
    assert response.status==200 and value['enabled'] is True
    assert value['mode']=='authorized_workbench' and value['subscription_authorization'] is True
