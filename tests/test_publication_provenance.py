import pytest
from test_platform_business import secured,sign_in
from test_platform_login import runtime


@pytest.mark.parametrize('user,status',[('usr_local_test',403),('usr_other',403),('usr_engineer',200),('usr_manager',200)])
def test_provenance_requires_current_scene_management_and_preview(secured,user,status):
    _,client,_,_,_,_,_,_,old,new=secured
    path=f"/publications/{new['id']}/api/provenance"
    assert client.get(path).status_code==401
    sign_in(secured,user)
    response=client.get(path)
    assert response.status_code==status,response.text
    if status==200:
        assert response.json()['publication_id']==new['id']
        assert response.json()['package_generated'] is False
        assert response.headers['cache-control']=='no-store'
    assert client.get(path+'?space_id=foreign').status_code==403
    assert client.post(path).status_code==403


def test_provenance_rechecks_revocation_and_does_not_fall_back(secured):
    _,client,_,_,_,_,_,policies,old,new=secured
    sign_in(secured,'usr_engineer')
    path=f"/publications/{new['id']}/api/provenance"
    assert client.get(path).status_code==200
    revision,policy=policies.load()
    value=policy.model_dump();value['grants']=[g for g in value['grants'] if g['subject']!='usr_engineer']
    from packages.service.space_access import SpaceAccessPolicy
    policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=revision,actor='test',reason='revoke')
    assert client.get(path).status_code==403
