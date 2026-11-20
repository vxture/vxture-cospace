from test_platform_business import secured, sign_in
from test_platform_login import runtime

PATH='/api/ontology-resources'


def test_directory_read_write_authorization_and_fixed_detail(secured):
    _,client,*_=secured
    assert client.get(PATH).status_code==401
    headers,_=sign_in(secured,'usr_engineer')
    response=client.get(PATH+'?page_size=2')
    assert response.status_code==200,response.text
    data=response.json()
    assert len(data['items'])==2 and not data['can_group']
    assert 'history' not in data and 'definition' not in data['items'][0]
    ref=data['items'][0]['reference']
    assert client.get(PATH+'/definition',params=ref).status_code==200
    assert client.get(PATH+'?workspace_id=forged').status_code==422
    assert client.get(PATH+'?page=1&page=2').status_code==403
    body={'request_id':'a'*32,'module_id':ref['module_id'],'expected_revision':0,'group_ids':[]}
    assert client.post(PATH+'/membership',json=body,headers=headers).status_code==403
    headers,_=sign_in(secured,'usr_manager')
    assert client.get(PATH).json()['can_group']
    assert client.post(PATH+'/membership',json=body).status_code==403
    assert client.post(PATH+'/membership',json=body,headers=headers).status_code==200
    assert client.post(PATH+'/membership',json=body,headers=headers).json()['revision']==1
    assert client.post(PATH+'/membership',json={**body,'request_id':'b'*32},headers=headers).status_code==409
    assert client.get(PATH+'?snapshot='+data['snapshot']).status_code==409
    assert client.get(PATH+'/definition',params={**ref,'version':'9.0.0'}).status_code==409
