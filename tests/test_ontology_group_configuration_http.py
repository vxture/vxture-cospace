import pytest
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_ontology_group_configuration import change

PATH='/api/ontology-configuration/groups'


def test_groups_require_login_and_manager_and_csrf(secured):
    _,client,*_=secured
    assert client.get(PATH).status_code==401
    for user in ['usr_local_test','usr_engineer','usr_other']:
        headers,_=sign_in(secured,user)
        assert client.get(PATH).status_code==403
        assert client.post(PATH,json=change(),headers=headers).status_code==403
    headers,_=sign_in(secured,'usr_manager')
    assert client.get(PATH).status_code==200
    assert client.post(PATH,json=change()).status_code==403
    result=client.post(PATH,json=change(),headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['revision']==1 and result.headers['cache-control']=='no-store'
    assert client.post(PATH,json=change(),headers=headers).json()['revision']==1
    assert client.post(PATH,json=change(request_id='b'*32),headers=headers).status_code==409
    assert client.post(PATH,json=change(request_id='b'*32,expected_revision=1,name='  '),headers=headers).status_code==422
    assert client.get(PATH+'?workspace_id=spoofed').status_code==422
    assert client.post(PATH,json=change(scope='forged'),headers=headers).status_code==422
    assert client.request('DELETE',PATH,headers=headers).status_code==403


def test_configuration_is_independent_of_scene_and_definition_stores(secured,monkeypatch):
    _,client,_,_,_,directory,*_=secured
    sign_in(secured,'usr_manager')
    monkeypatch.setattr(directory,'list',lambda *args:pytest.fail('configuration read scenes'))
    monkeypatch.setattr('packages.service.platform_business_http.WorkspaceOntologies',lambda *args:pytest.fail('configuration accessed legacy ontology store'))
    response=client.get(PATH)
    assert response.status_code==200,response.text
    assert len(response.json()['groups'])==7


def test_manager_move_uses_same_csrf_and_revision_guards(secured):
    _,client,*_=secured
    headers,_=sign_in(secured,'usr_manager')
    before=client.get(PATH).json()
    target=before['groups'][-1]['group_id']
    body={'request_id':'d'*32,'expected_revision':0,'group_id':target,'move':'top','reason':'调整分组顺序：置顶'}
    assert client.post(PATH,json=body).status_code==403
    result=client.post(PATH,json=body,headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['groups'][0]['group_id']==target
    assert client.post(PATH,json=body,headers=headers).json()['revision']==1
    assert client.post(PATH,json={**body,'request_id':'e'*32},headers=headers).status_code==409
