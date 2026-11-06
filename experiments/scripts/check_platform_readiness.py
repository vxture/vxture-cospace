"""Read-only IdP/public-key and local configuration check; never prints credentials."""
import argparse
import json
import os
from pathlib import Path
from urllib.request import Request,build_opener
from datetime import datetime,timezone
from packages.infrastructure.platform_identity import NoRedirect,PlatformVerifierConfig,PlatformTokenVerifier
from packages.infrastructure.platform_rp import RpConfig
from packages.service.platform_login import LOGIN_SCOPES

REQUIRED=('COSPACE_OIDC_CLIENT_ID','COSPACE_OIDC_CLIENT_SECRET','COSPACE_ORIGIN','COSPACE_SESSION_KEY')


def check(issuer,fetch,env):
    PlatformVerifierConfig(issuer=issuer,audience='configuration-probe',jwks_url=issuer+'/oidc/jwks')
    discovery=fetch(issuer+'/.well-known/openid-configuration')
    required={'issuer':issuer,'authorization_endpoint':issuer+'/oidc/authorize',
              'token_endpoint':issuer+'/oidc/token','jwks_uri':issuer+'/oidc/jwks'}
    compatible=(all(discovery.get(k)==v for k,v in required.items()) and
        all(g in discovery.get('grant_types_supported',[]) for g in ('authorization_code','refresh_token')) and
        'RS256' in discovery.get('id_token_signing_alg_values_supported',[]) and
        'client_secret_basic' in discovery.get('token_endpoint_auth_methods_supported',[]) and
        'S256' in discovery.get('code_challenge_methods_supported',[]) and
        all(scope in discovery.get('scopes_supported',[]) for scope in LOGIN_SCOPES))
    keys=PlatformTokenVerifier(PlatformVerifierConfig(issuer=issuer,audience='configuration-probe',jwks_url=required['jwks_uri']),fetch=fetch)
    keys._refresh()
    missing=[n for n in REQUIRED if not env.get(n)]
    return {'profile':'cospace.platform-readiness/0.1','checked_at':datetime.now(timezone.utc).isoformat(),
        'issuer':issuer,'public_oidc_contract_compatible':compatible,'verification_keys':len(keys.keys),
        'token_exchange_advertised':'urn:ietf:params:oauth:grant-type:token-exchange' in discovery.get('grant_types_supported',[]),
        'requested_login_scopes':list(LOGIN_SCOPES),
        'requested_login_scopes_supported':all(scope in discovery.get('scopes_supported',[]) for scope in LOGIN_SCOPES),
        'missing_environment_names':missing,'client_configuration_present':not missing,
        'real_login_verified':False,'workspace_permissions_verified':False,'service_token_exchange_verified':False,
        'status':('contract_incompatible' if not compatible else 'external_configuration_required' if missing else 'real_login_and_workspace_acceptance_required')}


def fetch(url):
    with build_opener(NoRedirect()).open(Request(url,headers={'Accept':'application/json'}),timeout=10) as r:
        raw=r.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('platform_metadata_budget')
        return json.loads(raw)


def main():
    p=argparse.ArgumentParser();p.add_argument('--issuer',default='https://accounts.vxture.com');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.exit(2,'exclusive_report_required\n')
    try:
        result=check(a.issuer,fetch,os.environ)
        if result['client_configuration_present']:
            RpConfig.from_env()
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
    except Exception:p.exit(2,'platform_readiness_check_failed; no credentials or remote response logged\n')

if __name__=='__main__':main()
