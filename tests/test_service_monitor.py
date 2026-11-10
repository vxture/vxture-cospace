import json
import sqlite3
import pytest
from packages.infrastructure.platform_identity import PlatformPrincipal
from packages.service.service_monitor import ServiceMonitor
from test_online_consumer import consumer
from test_platform_business import secured, sign_in
from test_platform_login import runtime, login


def principal(org='org_mock', workspace='ws_mock', issuer='https://issuer.test'):
    return PlatformPrincipal(issuer, 'usr_manager', org, workspace, (), 'user', 9999999999)


def test_persistent_scoped_bounded_observations(tmp_path, monkeypatch):
    clock=[1000000.]
    monitor=ServiceMonitor(tmp_path, now=lambda:clock[0]);p=principal()
    scope=(p.issuer,p.org_id,p.workspace_id,'space-a','robot-product')
    monitor.record(scope,'preview-a','historical_result',200,10)
    monitor.record(scope,'preview-b','observation_time_unverified',200,20)
    for changed in [(p.issuer,'other',p.workspace_id,'space-a','secret-caller'),(p.issuer,p.org_id,'other','space-a','secret-caller'),('other',p.org_id,p.workspace_id,'space-a','secret-caller'),(p.issuer,p.org_id,p.workspace_id,'space-b','secret-caller')]:
        monitor.record(changed,'foreign','historical_result',200,100)
    persisted=ServiceMonitor(tmp_path, now=lambda:clock[0])
    result=persisted.snapshot(p,'space-a')
    assert result['request_count']==2 and result['counts']=={'historical_result':1,'refused':1,'rejected':0,'failed':0}
    assert result['p95_ms']==20 and 'secret-caller' not in json.dumps(result)
    assert {v['publication_id'] for v in result['versions']}=={'preview-a','preview-b'}
    # Window expiry and actual retention deletion are separate.
    clock[0]+=86401
    assert persisted.snapshot(p,'space-a')['request_count']==0
    clock[0]+=7*86400
    persisted.snapshot(p,'space-a')
    with sqlite3.connect(persisted.path) as db:assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==0
    monkeypatch.setattr('packages.service.service_monitor.MAX_EVENTS',2)
    for index in range(4):
        clock[0]+=1;persisted.record(scope,f'preview-{index}','historical_result',200,10)
    capped=persisted.snapshot(p,'space-a')
    assert capped['request_count']==2 and capped['coverage']['partial'] and capped['coverage']['truncated_before']
    assert {r['publication'] for r in capped['recent']}=={'preview-2','preview-3'}


def test_only_verified_authorized_s2s_requests_are_recorded(consumer):
    client,route,body,headers,path,config,access,jobs,spaces,old,new,claims,accounts,clock=consumer
    assert client.post(route,json=body).status_code==401
    assert client.post(route,json=body,headers=headers|{'Origin':access.rp.config.origin}).status_code==403
    path.write_text(json.dumps(config|{'grants':[]}))
    assert client.post(route,json=body,headers=headers).status_code==403
    path.write_text(json.dumps(config))
    assert client.post(route,json=body,headers=headers).status_code==200
    assert client.post(route,json=body|{'mode':'operational'},headers=headers).json()['status']=='refused'
    assert client.post(route,json=body|{'frame_id':'wrong'},headers=headers).status_code==409
    client.follow_redirects=False;accounts.subject='usr_manager';login(access.rp,client,accounts)
    result=client.get('/api/service-monitor',params={'space_id':spaces[0]['id']})
    assert result.status_code==200,result.text
    report=result.json()
    assert report['request_count']==3 and report['counts']=={'historical_result':1,'refused':1,'rejected':1,'failed':0}
    assert report['configuration']=={'state':'configured','callers':['robot-product']}
    assert report['recent'][0]['outcome']=='consumer_frame_mismatch'
    assert client.get('/api/service-monitor',params={'space_id':spaces[1]['id']}).status_code==403
    assert client.get('/api/service-monitor',params={'space_id':spaces[0]['id'],'extra':'x'}).status_code==422
    raw=access.service_monitor.path.read_bytes()
    assert headers['Authorization'].encode() not in raw
    assert b'point_m' not in raw and b'model_manifest_sha256' not in raw


@pytest.mark.parametrize('user,expected',[('usr_local_test',403),('usr_engineer',403),('usr_other',403),('usr_manager',200)])
def test_monitor_requires_scene_publication_management(secured,user,expected):
    _,client,_,_,_,_,spaces,*_=secured
    assert client.get('/api/service-monitor',params={'space_id':spaces[0]['id']}).status_code==401
    sign_in(secured,user)
    response=client.get('/api/service-monitor',params={'space_id':spaces[0]['id']})
    assert response.status_code==expected,response.text
    if expected==200:
        assert response.json()['configuration']=={'state':'not_configured','callers':[]}
        assert response.json()['request_count']==0


def test_monitor_failures_do_not_break_consumption_or_fake_zero(consumer,monkeypatch):
    client,route,body,headers,path,config,access,jobs,spaces,old,new,claims,accounts,clock=consumer
    def unavailable():raise sqlite3.OperationalError('local disk unavailable')
    monkeypatch.setattr(access.service_monitor,'connect',unavailable)
    response=client.post(route,json=body,headers=headers)
    assert response.status_code==200 and response.json()['status']=='historical_result'
    assert access.service_monitor.write_failed_at is not None
    client.follow_redirects=False;accounts.subject='usr_manager';login(access.rp,client,accounts)
    assert client.get('/api/service-monitor',params={'space_id':spaces[0]['id']}).status_code==503
    monkeypatch.undo()
    report=client.get('/api/service-monitor',params={'space_id':spaces[0]['id']}).json()
    assert report['coverage']['partial'] and report['coverage']['write_failed_at']


def test_monitor_config_revocation_and_pause_are_distinct(consumer):
    from packages.service.preview_publications import PreviewPublications
    from test_preview_control import run
    client,route,body,headers,path,config,access,jobs,spaces,old,new,claims,accounts,clock=consumer
    run(jobs.controls,PreviewPublications(jobs),spaces[0]['id'],'publication:'+new['id'],'pause_distribution')
    assert client.post(route,json=body,headers=headers).status_code==409
    client.follow_redirects=False;accounts.subject='usr_manager';login(access.rp,client,accounts)
    report=client.get('/api/service-monitor',params={'space_id':spaces[0]['id']}).json()
    assert report['recent'][0]['outcome']=='publication_distribution_paused'
    assert report['counts']['rejected']==1 and report['counts']['refused']==0
    path.write_text(json.dumps(config|{'grants':[]}))
    report=client.get('/api/service-monitor',params={'space_id':spaces[0]['id']}).json()
    assert report['configuration']=={'state':'not_granted','callers':[]}
    path.write_text('{broken')
    report=client.get('/api/service-monitor',params={'space_id':spaces[0]['id']}).json()
    assert report['configuration']=={'state':'unavailable','callers':[]}
    assert report['request_count']==1
