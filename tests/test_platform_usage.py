from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from packages.infrastructure.platform_usage import UsageTransport, StorageInventory, StorageReporter
from packages.infrastructure.platform_subscription import SubscriptionUnavailable
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.service.space_access import SpaceAccessPolicy
from packages.service.platform_auth_http import create_auth_app
from test_platform_subscription import config
from test_platform_login import runtime

STAMP='2026-11-06T12:00:00+00:00'
PRINCIPAL=SimpleNamespace(issuer='https://accounts.vxture.com',org_id='org_mock',workspace_id='ws_mock')


def transport(monkeypatch, payload, *, status=200):
    import packages.infrastructure.platform_usage as module
    obj=UsageTransport.__new__(UsageTransport);obj.config=config()
    obj.rp=SimpleNamespace(config=SimpleNamespace(issuer=PRINCIPAL.issuer))
    obj.token=lambda p:'test-only-bearer'
    requests=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self,*_):return payload
    Response.status=status
    class Opener:
        def open(self,request,timeout):
            assert timeout==5
            requests.append(request);return Response()
    monkeypatch.setattr(module,'build_opener',lambda *args:Opener())
    return obj,requests


@pytest.mark.parametrize('applied',[True,False])
def test_gauge_absolute_observation_and_lww_reply(monkeypatch,applied):
    reply=dict(workspace_id='ws_mock',product='cospace',metric='storage.bytes',value='42',observed_at=STAMP,applied=applied)
    obj,requests=transport(monkeypatch,json.dumps(reply).encode())
    assert obj.gauge(PRINCIPAL,42,STAMP)==reply
    request=requests[0]
    assert request.full_url=='https://internal.example/usage/gauge'
    assert request.method=='PUT'
    assert json.loads(request.data)==dict(workspace_id='ws_mock',product='cospace',metric='storage.bytes',value=42,observed_at=STAMP)
    assert request.get_header('Authorization')=='Bearer test-only-bearer'


@pytest.mark.parametrize('value',[-1,True,1.5,2**53])
def test_invalid_gauge_is_never_sent(monkeypatch,value):
    obj,requests=transport(monkeypatch,b'{}')
    with pytest.raises(ValueError):obj.gauge(PRINCIPAL,value,STAMP)
    assert not requests


def test_counter_retry_reuses_business_key_and_gated_is_information(monkeypatch):
    # This is a mock-only future counter, not a registered commercial metric.
    obj,requests=transport(monkeypatch,b'{"gated":true,"reason":"quota_exhausted"}')
    for _ in range(2):
        assert obj.consume(PRINCIPAL,'test.counter',1,'operation:one')['gated'] is True
    assert requests[0].data==requests[1].data
    assert json.loads(requests[0].data)['intent']=='report'
    assert requests[0].method=='POST' and requests[0].full_url.endswith('/usage/consume')


@pytest.mark.parametrize('metric',['storage.bytes','member.max','scene.max','ai.credit','Bad Metric'])
def test_gauge_allowance_and_delegated_ai_cannot_be_consumed(monkeypatch,metric):
    obj,requests=transport(monkeypatch,b'{}')
    with pytest.raises(ValueError):obj.consume(PRINCIPAL,metric,1,'operation:one')
    assert not requests


@pytest.mark.parametrize('payload,status',[(b'secret-provider-body',500),(b'[]',200),
    (b'{"applied":true,"applied":false}',200),(b'x'*1_048_577,200),
    (b'{"workspace_id":"foreign","product":"cospace","metric":"storage.bytes","applied":true}',200)],
    ids=['http-error','non-object','duplicate-key','oversize','foreign-workspace'])
def test_usage_response_failures_are_private(monkeypatch,payload,status):
    obj,_=transport(monkeypatch,payload,status=status)
    with pytest.raises(SubscriptionUnavailable) as error:obj.gauge(PRINCIPAL,0,STAMP)
    assert 'secret-provider-body' not in str(error.value)


def test_consume_success_and_incomplete_response(monkeypatch):
    obj,_=transport(monkeypatch,b'{"consumed":1,"remaining_total":99}')
    assert obj.consume(PRINCIPAL,'test.counter',1,'key')['consumed']==1
    obj,_=transport(monkeypatch,b'{}')
    with pytest.raises(SubscriptionUnavailable):obj.consume(PRINCIPAL,'test.counter',1,'key')


def test_foreign_issuer_or_malformed_workspace_is_not_sent(monkeypatch):
    obj,requests=transport(monkeypatch,b'{}')
    for changes in ({'issuer':'https://other.example'},{'workspace_id':'../foreign'}):
        principal=SimpleNamespace(**(vars(PRINCIPAL)|changes))
        with pytest.raises(SubscriptionUnavailable):obj.gauge(principal,0,STAMP)
    assert not requests


@pytest.fixture
def inventory(tmp_path):
    root=tmp_path/'business';root.mkdir()
    input_root=root/'preview-inputs';input_root.mkdir()
    job_root=root/'preview-builds';job_root.mkdir()
    policies=SpacePolicyStore(tmp_path/'auth')
    bindings=[dict(issuer=PRINCIPAL.issuer,org_id='org_mock',workspace_id=workspace,
        space_id='space-'+str(number)*16) for number,workspace in [(1,'ws_mock'),(2,'ws_other'),(3,'ws_empty')]]
    policies.replace(SpaceAccessPolicy(bindings=bindings,grants=[]),expected_revision=0,actor='test',reason='test')
    def read(identity):return json.loads((input_root/(identity+'.json')).read_bytes())
    obj=StorageInventory(policies,SimpleNamespace(root=input_root,read_original=read),SimpleNamespace(root=job_root))
    return obj,root


def put(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(content if isinstance(content,bytes) else json.dumps(content).encode())
    return path


def rows(obj):return {p.workspace_id:value for p,value,_ in obj.snapshot()}


def test_inventory_workspace_isolation_dedup_zero_and_retained_versions(inventory):
    obj,root=inventory
    source=put(root/'preview-inputs/uploads/scene/source/cloud.ply',b'12345').parent
    record=dict(space_id='space-'+'1'*16,snapshot=str(source))
    put(root/'preview-inputs/input-one.json',record)
    put(root/'preview-inputs/input-two.json',record)  # Same bytes, one Workspace.
    put(root/'preview-builds/build-one/job.json',dict(space_id='space-'+'1'*16,state='retired'))
    put(root/'preview-builds/build-one/output/cloud.ply',b'1234567')
    put(root/'preview-builds/publications/preview-one/publication.json',dict(space_id='space-'+'2'*16))
    put(root/'preview-builds/publications/preview-one/model.ply',b'123')
    put(root/'preview-builds/build-unassigned/job.json',{})
    put(root/'preview-builds/build-unassigned/output/cloud.ply',b'unassigned')
    put(root/'.upload-staging/temp',b'temporary')
    put(root/'preview-ontologies/global.json',b'global')
    values=rows(obj)
    assert values['ws_mock']==5+sum(p.stat().st_size for p in (root/'preview-builds/build-one').rglob('*') if p.is_file())
    assert values['ws_other']==sum(p.stat().st_size for p in (root/'preview-builds/publications/preview-one').rglob('*') if p.is_file())
    assert values['ws_empty']==0
    (source/'cloud.ply').write_bytes(b'1')
    assert rows(obj)['ws_mock']==values['ws_mock']-4  # Absolute measurement supports decreases.


def test_missing_or_external_input_never_reports_partial_zero(inventory,tmp_path):
    obj,root=inventory
    path=put(root/'preview-inputs/input-one.json',dict(space_id='space-'+'1'*16,snapshot=str(root/'missing')))
    with pytest.raises(SubscriptionUnavailable):obj.snapshot()
    path.write_text(json.dumps(dict(space_id='space-'+'1'*16,snapshot=str(tmp_path/'outside'))))
    with pytest.raises(SubscriptionUnavailable):obj.snapshot()


def test_shared_payload_between_workspaces_is_ambiguous(inventory):
    obj,root=inventory
    source=put(root/'source/cloud.ply',b'payload').parent
    for number in (1,2):
        put(root/f'preview-inputs/input-{number}.json',dict(space_id='space-'+str(number)*16,snapshot=str(source)))
    with pytest.raises(SubscriptionUnavailable):obj.snapshot()


def test_symlink_and_parent_traversal_rejected(inventory):
    obj,root=inventory
    source=put(root/'source/cloud.ply',b'payload').parent
    path=put(root/'preview-inputs/input-one.json',dict(space_id='space-'+'1'*16,snapshot=str(root/'source/../source')))
    with pytest.raises(SubscriptionUnavailable):obj.snapshot()
    try:(root/'linked').symlink_to(source,target_is_directory=True)
    except OSError:pytest.skip('symlink creation unavailable on this host')
    path.write_text(json.dumps(dict(space_id='space-'+'1'*16,snapshot=str(root/'linked'))))
    with pytest.raises(SubscriptionUnavailable):obj.snapshot()


def test_reporter_retries_next_snapshot_and_does_not_block_other_workspaces(inventory):
    obj,_=inventory;calls=[];offline=[True]
    def gauge(principal,value,stamp):
        calls.append((principal.workspace_id,value,stamp))
        if principal.workspace_id=='ws_mock' and offline[0]:raise SubscriptionUnavailable('offline')
    reporter=StorageReporter(obj,SimpleNamespace(gauge=gauge))
    with pytest.raises(SubscriptionUnavailable):reporter.run_once()
    assert len(calls)==3
    offline[0]=False
    assert reporter.run_once()==3
    assert all(value==0 for _,value,_ in calls)


def test_lifespans_start_and_stop_both_workers(runtime):
    rp=runtime[0];events=[]
    class Worker:
        def __init__(self,name):self.name=name
        @asynccontextmanager
        async def lifespan(self,app):
            events.append(self.name+' start')
            try:yield
            finally:events.append(self.name+' stop')
    with TestClient(create_auth_app(rp,reconciler=Worker('provisioning'),usage_reporter=Worker('usage'))):
        assert events==['provisioning start','usage start']
    assert events[-2:]==['usage stop','provisioning stop']
