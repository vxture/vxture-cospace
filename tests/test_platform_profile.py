from packages.service.platform_profile import profile_claims
from test_platform_login import runtime, login


def test_only_display_fields_are_projected():
    result = profile_claims({'email': 'person@example.test', 'phone': '+8613800000000',
        'phone_verified': True, 'email_verified': 'true', 'active_org_name': '示例单位',
        'active_workspace_name': '示例工作区', 'roles': ['admin'], 'access_token': 'never-return',
        'picture': 'https://accounts.vxture.com/avatar/example?v=1'})
    assert result == {'email': 'person@example.test', 'phone': '+8613800000000',
        'phone_verified': True, 'org_name': '示例单位', 'workspace_name': '示例工作区',
        'avatar_url': 'https://accounts.vxture.com/avatar/example?v=1'}


def test_bad_avatar_and_profile_values_are_omitted():
    for picture in ['javascript:alert(1)', 'data:image/png;base64,abc', '//foreign.test/a',
                    'http://foreign.test/a', 'https://user:password@foreign.test/a',
                    'https://foreign.test/a\nheader', 'https://[broken']:
        assert 'avatar_url' not in profile_claims({'picture': picture})
    assert profile_claims({'email': ['wrong'], 'phone': 'bad\nvalue', 'active_org_name': 'x'*501}) == {}


def test_signed_profile_reaches_current_and_existing_sessions(runtime):
    rp, client, accounts, _ = runtime
    accounts.profile_claims = {'email': 'person@example.test', 'phone': '+8613800000000',
                              'phone_verified': True, 'active_org_name': '示例单位'}
    _, sid = login(rp, client, accounts)
    public = client.get('/api/auth/session').json()
    assert public['user']['email'] == 'person@example.test'
    assert public['user']['org_name'] == '示例单位'
    assert public['user']['phone_verified'] is True
    assert 'access_token' not in public
    saved = rp.store.get('session', sid)
    saved.pop('profile')
    rp.store.put('session', sid, saved)
    assert client.get('/api/auth/session').json()['user']['phone'] == '+8613800000000'
