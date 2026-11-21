from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from packages.infrastructure.atlas_gateway import AtlasUnavailable
from packages.service.coordinate_assistance import AssistanceRequest, suggest
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_preview_pointcloud import specimen
from packages.data.input_coordinates import InputCoordinates


TEXT='导出说明：X向右，Y向前，Z向上，单位米。'
PROPOSAL={'axes':[{'direction':direction,'evidence_quote':quote} for direction,quote in
    [('right','X向右'),('forward','Y向前'),('up','Z向上')]],'unit':'m','unit_evidence_quote':'单位米','unresolved':[]}


def request(space='space-'+'a'*16, **extra):
    return {'space_id':space,'request_id':'a'*32,'evidence_text':TEXT}|extra


def test_model_is_advisory_has_exact_source_quotes_and_no_write_authority():
    calls=[]
    def chat(*args):calls.append(args);return '```json\n'+json.dumps(PROPOSAL,ensure_ascii=False)+'\n```'
    result=suggest(SimpleNamespace(chat=chat),'principal','private-ticket',AssistanceRequest(**request()))
    assert result['can_apply_axes'] and result['requires_confirmation'] and not result['coordinate_transform_applied']
    assert result['proposal']==PROPOSAL
    assert calls[0][2]=='cospace-coordinate-'+'a'*32
    assert json.loads(calls[0][3][1]['content'])=={'source_text':TEXT}


@pytest.mark.parametrize('mutation', [
    lambda p:p['axes'][0].update(evidence_quote='invented quotation'),
    lambda p:p['axes'][0].update(direction='execute_shell'),
    lambda p:p.update(unit_evidence_quote='mm'),
    lambda p:p.update(extra_action='publish'),
    lambda p:p['axes'][0].update(direction=None),
    lambda p:p.update(unresolved=['x'*241]),
])
def test_hallucinated_quotes_actions_unbounded_text_and_unknown_shapes_rejected(mutation):
    proposal=deepcopy(PROPOSAL);mutation(proposal)
    with pytest.raises(AtlasUnavailable,match='invalid_response'):
        suggest(SimpleNamespace(chat=lambda *a:json.dumps(proposal)),'p','token',AssistanceRequest(**request()))


@pytest.mark.parametrize('axes,unit,expected', [
    (['right','forward','up'],'m',True),
    (['right','forward','down'],'m',False),
    (['right','north','up'],'m',False),
    (['right',None,'up'],'m',False),
    (['right','forward','up'],'mm',False),
    (['right','forward','up'],None,False),
])
def test_rule_checks_still_gate_model_proposals(axes,unit,expected):
    proposal=deepcopy(PROPOSAL);text=TEXT+' 原文含有下、北、毫米。'
    proposal['unit']=unit;proposal['unit_evidence_quote']='' if unit is None else '毫米' if unit=='mm' else '单位米'
    for axis,direction in zip(proposal['axes'],axes):
        axis['direction']=direction
        if direction is None:axis['evidence_quote']=''
        if direction in ('down','north'):axis['evidence_quote']='下' if direction=='down' else '北'
    result=suggest(SimpleNamespace(chat=lambda *a:json.dumps(proposal)),'p','token',AssistanceRequest(**request(evidence_text=text)))
    assert result['can_apply_axes'] is expected


def test_model_with_unresolved_conflicts_cannot_offer_direct_application():
    proposal=deepcopy(PROPOSAL);proposal['unresolved']=['说明包含相互矛盾的坐标约定，请核对。']
    result=suggest(SimpleNamespace(chat=lambda *a:json.dumps(proposal)),'p','token',AssistanceRequest(**request()))
    assert not result['can_apply_axes']


def test_denied_and_csrf_requests_cannot_reach_model(secured,monkeypatch):
    _,client,_,_,_,_,spaces,*_=secured;calls=[]
    monkeypatch.setattr('packages.infrastructure.atlas_gateway.AtlasGateway.chat',lambda *a:calls.append(a))
    assert client.post('/api/coordinate-assistance',json=request(spaces[0]['id'])).status_code==401
    headers,_=sign_in(secured)
    assert client.post('/api/coordinate-assistance',json=request(spaces[0]['id']),headers=headers).status_code==403
    headers,_=sign_in(secured,'usr_engineer')
    assert client.post('/api/coordinate-assistance',json=request(spaces[0]['id'])).status_code==403
    assert client.post('/api/coordinate-assistance',json=request(spaces[1]['id']),headers=headers).status_code==403
    assert calls==[]


def test_bound_advisory_does_not_write_input_or_accept_stale_revisions(secured,tmp_path,monkeypatch):
    _,client,_,_,jobs,_,spaces,*_=secured;headers,_=sign_in(secured,'usr_engineer');space=spaces[0]['id']
    source=specimen(tmp_path);original=jobs.inputs.register('legacy',source,None,space,'ply_pointcloud')
    before=(jobs.inputs.root/(original['id']+'.json')).read_bytes();calls=[]
    def chat(*args):calls.append(args);return json.dumps(PROPOSAL)
    monkeypatch.setattr('packages.infrastructure.atlas_gateway.AtlasGateway.chat',chat)
    body=request(space,input_id=original['id'],expected_revision=0)
    result=client.post('/api/coordinate-assistance',json=body,headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['input_id']==original['id'] and result.json()['can_apply_axes']
    assert (jobs.inputs.root/(original['id']+'.json')).read_bytes()==before
    assert not InputCoordinates(jobs.inputs).path.exists()
    assert len(calls)==1 and calls[0][1].subject=='usr_engineer'
    assert client.post('/api/coordinate-assistance',json=body|{'expected_revision':1},headers=headers).status_code==409
    assert client.post('/api/coordinate-assistance',json=body|{'tenantId':'forged'},headers=headers).status_code==422
    assert client.post('/api/coordinate-assistance',json=body|{'evidence_text':' '*100},headers=headers).status_code==422
    assert client.post('/api/coordinate-assistance',json=body|{'evidence_text':'x'*12001},headers=headers).status_code==422
    assert len(calls)==1


def test_unconfigured_capability_and_unsupported_route_are_honest(secured):
    _,client,_,_,_,_,spaces,*_=secured;headers,_=sign_in(secured,'usr_engineer');space=spaces[0]['id']
    response=client.get('/api/coordinate-assistance',params={'space_id':space})
    assert response.status_code==200 and response.json()['available'] is False
    response=client.post('/api/coordinate-assistance',json=request(space),headers=headers)
    assert response.status_code==503 and response.json()['detail']=='coordinate_ai_unconfigured'
