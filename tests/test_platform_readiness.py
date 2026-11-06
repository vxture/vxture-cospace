import pytest
from experiments.scripts.check_platform_readiness import check,REQUIRED
from test_platform_identity import keys,ISSUER


@pytest.mark.parametrize('change',[{}, {'token_endpoint':'https://evil.example'}, {'grant_types_supported':[]},
                                  {'scopes_supported':['openid','profile']}])
def test_public_readiness_never_claims_actual_login_or_exposes_secret(keys,change):
    meta={'issuer':ISSUER,'authorization_endpoint':ISSUER+'/oidc/authorize','token_endpoint':ISSUER+'/oidc/token',
        'jwks_uri':ISSUER+'/oidc/jwks','grant_types_supported':['authorization_code','refresh_token','urn:ietf:params:oauth:grant-type:token-exchange'],
        'id_token_signing_alg_values_supported':['RS256'],'token_endpoint_auth_methods_supported':['client_secret_basic'],
        'code_challenge_methods_supported':['S256'],'scopes_supported':['openid','profile','email','phone']}|change
    result=check(ISSUER,lambda url:{'keys':[keys[0].as_dict(private=False)]} if url.endswith('/oidc/jwks') else meta,
                 {'COSPACE_OIDC_CLIENT_SECRET':'never-print-this'})
    assert result['public_oidc_contract_compatible']==(not change)
    assert result['status']==('contract_incompatible' if change else 'external_configuration_required')
    assert result['missing_environment_names']==[n for n in REQUIRED if n!='COSPACE_OIDC_CLIENT_SECRET']
    assert not any(result[k] for k in ('real_login_verified','workspace_permissions_verified','service_token_exchange_verified'))
    assert 'never-print-this' not in str(result)
    assert result['requested_login_scopes']==['openid','profile','email']
