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
    assert {item['outcome']:item['requests'] for item in report['outcomes']}=={'historical_result':1,'observation_time_unverified':1,'consumer_frame_mismatch':1}
    assert report['callers'][0]['requests']==3 and report['callers'][0]['caller']=='robot-product'
    assert report['assurance']['end_to_end_probe'] is False
    assert all(version['publication_id'] in (old['id'],new['id']) for version in report['assurance']['releases']['versions'])
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


def test_whole_window_diagnostics_include_events_outside_recent_page(tmp_path):
    monitor=ServiceMonitor(tmp_path,now=lambda:1000000.)
    p=principal();scope=(p.issuer,p.org_id,p.workspace_id,'space-a','robot-product')
    monitor.record(scope,'preview-a','consumer_frame_mismatch',409,10)
    for _ in range(25):monitor.record(scope,'preview-a','historical_result',200,20)
    report=monitor.snapshot(p,'space-a')
    assert len(report['recent'])==20 and all(row['outcome']=='historical_result' for row in report['recent'])
    assert next(item for item in report['outcomes'] if item['outcome']=='consumer_frame_mismatch')['requests']==1
    assert report['callers'][0]['requests']==26


def test_assurance_versions_follow_lifecycle_and_isolate_foreign_scene(consumer,monkeypatch):
    from packages.service.preview_publications import PreviewPublications
    from test_preview_control import run
    client,route,body,headers,path,config,access,jobs,spaces,old,new,claims,accounts,clock=consumer
    # Monitoring must not open full geometry or perform a synthetic query.
    original_read=PreviewPublications.read
    monkeypatch.setattr(PreviewPublications,'read',lambda *args:pytest.fail('geometry must not be read'))
    client.follow_redirects=False;accounts.subject='usr_manager';login(access.rp,client,accounts)
    endpoint='/api/service-monitor?space_id='+spaces[0]['id']
    report=client.get(endpoint).json()
    releases=report['assurance']['releases']
    assert releases['state']=='observed' and releases['distributing_count']==2
    assert {v['publication_id'] for v in releases['versions']}=={old['id'],new['id']}
    assert all(v['realtime']=='unverified' for v in releases['versions'])
    assert next(check for check in report['assurance']['checks'] if check['key']=='freshness')['state']=='attention'
    monkeypatch.setattr(PreviewPublications,'read',original_read)
    run(jobs.controls,PreviewPublications(jobs),spaces[0]['id'],'publication:'+new['id'],'pause_distribution')
    monkeypatch.setattr(PreviewPublications,'read',lambda *args:pytest.fail('geometry must not be read'))
    report=client.get(endpoint).json()
    assert report['assurance']['releases']['distributing_count']==1
    assert next(v for v in report['assurance']['releases']['versions'] if v['publication_id']==new['id'])['state']=='paused'
    # A broken current-scene manifest is exposed as unknown, never healthy.
    (PreviewPublications(jobs).root/old['id']/'model.json').write_text('{}')
    report=client.get(endpoint).json()
    assert report['assurance']['releases']['distributing_count']==0
    assert next(v for v in report['assurance']['releases']['versions'] if v['publication_id']==old['id'])['state']=='unavailable'
    # A metadata read failure is explicit without removing request history.
    def unavailable(*args):raise OSError('unavailable')
    monkeypatch.setattr('packages.service.service_assurance.version_status',unavailable)
    report=client.get(endpoint).json()
    assert report['assurance']['releases']['state']=='unavailable'
    assert report['assurance']['releases']['distributing_count'] is None
    assert next(check for check in report['assurance']['checks'] if check['key']=='publication')['state']=='unknown'


def test_assurance_retired_version_preserves_replacement(consumer):
    from packages.service.preview_publications import PreviewPublications
    from packages.service.service_assurance import version_status
    from test_publication_retirement import request as retire
    client,route,body,headers,path,config,access,jobs,spaces,old,new,*_=consumer
    pubs=PreviewPublications(jobs)
    jobs.controls.change(pubs,retire(jobs,pubs,spaces[0]['id'],old,new),'test')
    result=version_status(jobs,spaces[0]['id'])
    version=next(v for v in result['versions'] if v['publication_id']==old['id'])
    assert version['state']=='retired' and version['replacement_publication_id']==new['id']
    assert result['distributing_count']==1
