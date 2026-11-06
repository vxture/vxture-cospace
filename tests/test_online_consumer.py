import json
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from packages.infrastructure.platform_identity import PlatformTokenVerifier,IdentityRejected
from packages.service.online_consumer import OnlineConsumer,ServiceTokens
from packages.service.online_client import ClientConfig,OnlineClient,GRANT
from packages.service.platform_auth_http import create_auth_app
from packages.service.platform_business_http import BusinessAccess
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_platform_business import secured
from test_platform_login import runtime
from test_platform_identity import keys,verifier,signed,NOW,ISSUER
from test_preview_control import run
from test_publication_retirement import request as retire
from packages.service.preview_publications import PreviewPublications


def service_claims(**changes):
    return dict(iss=ISSUER,aud='cospace',act={'sub':'robot-product'},mode='service',scope='tool:cospace',
                org_id='org_mock',workspace_id='ws_mock',jti='test-jti',iat=NOW,exp=NOW+300)|changes


@pytest.mark.parametrize('changes',[
    {'aud':['cospace']},{'aud':'yucer'},{'mode':'obo'},{'scope':'*'},{'scope':'tool:cospace extra'},
    {'sub':'usr_alice'},{'delegated':False},{'userType':'tenant_user'}, {'act':{'sub':'robot-product','extra':'x'}},
    {'act':{}},{'act':{'sub':'../evil'}},{'org_id':''},{'workspace_id':None},{'jti':None},
    {'exp':NOW},{'exp':NOW+301},{'iat':NOW+31,'exp':NOW+100},{'nbf':NOW+1},
])
def test_strict_service_token_kind_and_short_lifetime(keys,changes):
    with pytest.raises(IdentityRejected):ServiceTokens(verifier(keys)).verify(signed(keys[0],service_claims(**changes)),'cospace')


def test_service_cryptography_does_not_relax_human_verifier(keys):
    token=signed(keys[0],service_claims())
    assert ServiceTokens(verifier(keys)).verify(token,'cospace')['act']['sub']=='robot-product'
    with pytest.raises(IdentityRejected):verifier(keys).verify(token)
    with pytest.raises(IdentityRejected):verifier(keys).verify_id(token)


@pytest.fixture
def consumer(secured,tmp_path):
    rp,_,accounts,clock,jobs,directory,spaces,policies,old,new=secured
    config_path=tmp_path/'consumer.json'
    config={'profile':'cospace.online-consumer-access/0.1','audience':'cospace',
            'grants':[{'caller':'robot-product','space_id':spaces[0]['id']}]}
    config_path.write_text(json.dumps(config))
    access=BusinessAccess(rp,policies,directory,jobs,consumer_config=config_path)
    v=PlatformTokenVerifier(rp.config.verifier_config.model_copy(update={'audience':'cospace'}),now=lambda:clock[0])
    access.consumer.tokens=ServiceTokens(v)
    c=service_claims(iss=accounts.issuer,iat=clock[0],exp=clock[0]+300)
    from joserfc import jwt
    token=jwt.encode({'alg':'RS256','kid':accounts.key.kid},c,accounts.key)
    app=create_auth_app(rp,business=create_app(None,jobs,space_directory=directory,platform_origin=rp.config.origin),access=access)
    record,model=PreviewPublications(jobs).read(new['id'])
    body={'model_manifest_sha256':record['model_manifest_sha256'],'frame_id':model.manifest['frame_id'],
          'point_m':[(float(x)+0.5)*model.resolution for x in sorted(model.cells)[0]],'mode':'historical','max_age_s':60,'accept_unverified_time':True}
    route=f'/s2s/spaces/{spaces[0]["id"]}/publications/{new["id"]}/query'
    with TestClient(app,base_url=rp.config.origin) as client:
        yield client,route,body,{'Authorization':'Bearer '+token},config_path,config,access,jobs,spaces,old,new,c,accounts,clock


def test_historical_surface_unknown_and_operational_refusal(consumer):
    client,route,body,headers,*_=consumer
    r=client.post(route,json=body,headers=headers);assert r.status_code==200,r.text
    doc=r.json();assert doc['status']=='historical_result' and doc['as_of'] is doc['valid_until'] is None
    from pathlib import Path
    from jsonschema import Draft202012Validator
    Draft202012Validator(json.loads(Path('contracts/schemas/online-consumption-v0.1.schema.json').read_bytes())).validate(doc)
    assert not doc['robot_ready'] and doc['grade']=='unverified' and doc['result']['state']=='surface_candidate'
    unknown=client.post(route,json=body|{'point_m':[1000.,1000.,1000.]},headers=headers).json()
    assert unknown['result']['state']=='unknown' and unknown['completeness']['unknown']==1
    for changes in ({'mode':'operational'},{'accept_unverified_time':False}):
        refused=client.post(route,json=body|changes,headers=headers).json()
        assert refused['status']=='refused' and refused['result'] is None and refused['refusal']=='observation_time_unverified'


def test_dependency_unavailable_and_authority_changed_fail_closed(consumer,monkeypatch):
    client,route,body,headers,path,config,access,*_=consumer
    from packages.infrastructure.platform_identity import IdentityUnavailable
    monkeypatch.setattr(access.consumer.tokens.verifier,'fetch',lambda _:(_ for _ in ()).throw(OSError('offline')))
    assert client.post(route,json=body,headers=headers).status_code==503
    monkeypatch.undo()
    original=access.consumer.load;calls=[]
    def load():
        result=original();calls.append(True)
        return result if len(calls)==1 else result.model_copy(update={'grants':[]})
    monkeypatch.setattr(access.consumer,'load',load)
    assert client.post(route,json=body,headers=headers).status_code==503


@pytest.mark.parametrize('changes,code',[({'model_manifest_sha256':'0'*64},409),({'frame_id':'wrong'},409),
    ({'max_age_s':None},422),({'max_age_s':-1},422),({'point_m':[0.,0.]},422),({'free':True},422)])
def test_query_contract_required_pin_age_and_coordinates(consumer,changes,code):
    client,route,body,headers,*_=consumer
    r=client.post(route,json=body|changes,headers=headers);assert r.status_code==code,r.text


def test_cookie_browser_credentials_cannot_cross_interfaces(consumer):
    client,route,body,headers,*_=consumer
    assert client.post(route,json=body).status_code==401
    assert client.post(route,json=body,headers={'Cookie':'cospace_rp=stolen'}).status_code==401
    for extra in ({'Cookie':'cospace_rp=x'},{'Origin':'http://127.0.0.1:8768'}):
        assert client.post(route,json=body,headers=headers|extra).status_code==403
    assert client.get('/api/spaces',headers=headers).status_code==401
    assert client.post('/api/build-jobs',json={},headers=headers).status_code==401
    assert client.get(route,headers=headers).status_code==404
    assert client.post(route+'?token=x',json=body,headers=headers).status_code==404
    assert client.post(route,content='{}',headers=headers|{'Content-Type':'text/plain'}).status_code==415
    assert client.post(route,content='{"a":1,"a":2}',headers=headers|{'Content-Type':'application/json'}).status_code==422
    assert client.post(route,content='x'*8193,headers=headers|{'Content-Type':'application/json'}).status_code==413


@pytest.mark.parametrize('field,value',[('workspace_id','ws_other'),('org_id','org_other'),('act',{'sub':'another-product'})])
def test_signed_wrong_tenant_or_caller_denied(consumer,field,value):
    client,route,body,headers,path,config,access,jobs,spaces,old,new,claims,accounts,clock=consumer
    from joserfc import jwt
    token=jwt.encode({'alg':'RS256','kid':accounts.key.kid},claims|{field:value},accounts.key)
    assert client.post(route,json=body,headers={'Authorization':'Bearer '+token}).status_code==403


def test_scene_grants_live_revocation_and_broken_configuration(consumer):
    client,route,body,headers,path,config,access,jobs,spaces,*_=consumer
    path.write_text(json.dumps(config|{'grants':[]}))
    assert client.post(route,json=body,headers=headers).status_code==403
    path.write_text(json.dumps(config|{'grants':config['grants']*2}))
    assert client.post(route,json=body,headers=headers).status_code==503
    path.write_text(json.dumps(config))
    foreign=route.replace(spaces[0]['id'],spaces[1]['id'])
    path.write_text(json.dumps(config|{'grants':config['grants']+[{'caller':'robot-product','space_id':spaces[1]['id']}]}))
    assert client.post(foreign,json=body,headers=headers).status_code==403
    path.write_text('{broken')
    assert client.post(route,json=body,headers=headers).status_code==503


def test_expired_token_and_lifecycle_never_deliver(consumer):
    client,route,body,headers,path,config,access,jobs,spaces,old,new,claims,accounts,clock=consumer
    pubs=PreviewPublications(jobs);space=spaces[0]['id'];artifact='publication:'+new['id']
    run(jobs.controls,pubs,space,artifact,'pause_distribution')
    assert client.post(route,json=body,headers=headers).status_code==409
    run(jobs.controls,pubs,space,artifact,'restore')
    assert client.post(route,json=body,headers=headers).status_code==200
    jobs.controls.change(pubs,retire(jobs,pubs,space,new,kind='erroneous'),'test')
    assert client.post(route,json=body,headers=headers).status_code==409
    clock[0]+=300
    assert client.post(route,json=body,headers=headers).status_code==401


def test_independent_client_exchange_validate_and_reject_altered_reply(consumer):
    client,route,body,headers,path,config,access,jobs,spaces,old,new,claims,accounts,clock=consumer
    record,model=PreviewPublications(jobs).read(new['id'])
    cfg=ClientConfig(profile='cospace.online-consumer-client/0.1',issuer=accounts.issuer,api_origin=access.rp.config.origin,
        audience='cospace',caller='robot-product',org_id='org_mock',workspace_id='ws_mock',space_id=spaces[0]['id'],
        publication_id=new['id'],model_id=model.manifest['id'],model_manifest_sha256=record['model_manifest_sha256'],
        source_model_sha256=record['source_model_sha256'],frame_id=model.manifest['frame_id'],allow_loopback_http=True)
    accounts.service_clients['independent-test']={'secret':'local-test-only','caller':cfg.caller,'audience':cfg.audience,
                                                'org_id':cfg.org_id,'workspace_id':cfg.workspace_id}
    from packages.service.online_client import transport
    calls=[]
    def send(url,h,data):
        calls.append((url,set(h)))
        if url.endswith('/oidc/token'):return transport(url,h,data)
        return client.post(route,headers=h,content=data).json()
    worker=OnlineClient(cfg,'independent-test',SecretStr('local-test-only'),send=send,verifier=access.consumer.tokens.verifier)
    reply=worker.query(body['point_m'],mode='historical',max_age_s=60,accept_unverified_time=True)
    assert reply['status']=='historical_result' and len(calls)==2
    assert all('Cookie' not in h and 'Origin' not in h for _,h in calls)
    query=__import__('packages.service.online_consumer',fromlist=['Query']).Query.model_validate(body)
    for altered in ({'robot_ready':True},{'model_manifest_sha256':'0'*64},{'frame_id':'wrong'},
                    {'as_of':'2026-11-05T00:00:00Z'},{'status':'success'},{'result':reply['result']|{'state':'free'}}):
        with pytest.raises(ValueError):worker.validate(reply|altered,query)
    wrong=OnlineClient(cfg,'independent-test',SecretStr('wrong'),send=send,verifier=access.consumer.tokens.verifier)
    with pytest.raises(Exception):wrong.query([0.,0.,2.],mode='operational',max_age_s=60)
