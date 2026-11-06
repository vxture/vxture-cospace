"""Independent, cookie-free service consumer. No token persistence or refresh."""
import base64
import json
from urllib.parse import quote_plus,urlencode,urlsplit
from urllib.request import Request,build_opener,ProxyHandler
from pydantic import BaseModel,ConfigDict,Field,SecretStr,model_validator
from packages.infrastructure.platform_identity import PlatformVerifierConfig,PlatformTokenVerifier,NoRedirect,IdentityUnavailable
from packages.service.online_consumer import Query,ServiceTokens

GRANT='urn:ietf:params:oauth:grant-type:token-exchange'


class ClientConfig(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    profile:str=Field(pattern=r'^cospace.online-consumer-client/0\.1$')
    issuer:str
    api_origin:str
    audience:str=Field(pattern=r'^[a-z][a-z0-9-]{0,99}$')
    caller:str=Field(pattern=r'^[a-z][a-z0-9-]{0,99}$')
    org_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,160}$')
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,160}$')
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    publication_id:str=Field(pattern=r'^preview-[a-f0-9]{16}$')
    model_id:str=Field(min_length=1,max_length=160)
    model_manifest_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    source_model_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    frame_id:str=Field(min_length=1,max_length=160)
    allow_loopback_http:bool=False

    @model_validator(mode='after')
    def urls(self):
        for url in (self.issuer,self.api_origin):
            PlatformVerifierConfig(issuer=url,audience=self.audience,jwks_url=url+'/oidc/jwks',allow_loopback_http=self.allow_loopback_http)
            if urlsplit(url).path:raise ValueError('origin_only_required')
        return self


def transport(url,headers,data):
    """No redirects, proxies, cookie jars, or implicit retry of a credential."""
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(Request(url,data=data,headers=headers,method='POST'),timeout=10) as response:
            raw=response.read(1_048_577)
            if len(raw)>1_048_576 or response.headers.get_content_type()!='application/json':raise ValueError('consumer_response_budget_or_type')
            result=json.loads(raw)
            if not isinstance(result,dict):raise ValueError('consumer_response_not_object')
            return result
    except (OSError,ValueError) as exc:
        raise IdentityUnavailable('consumer_request_failed_no_remote_body_logged') from exc


class OnlineClient:
    def __init__(self,config,client_id,client_secret,*,send=transport,verifier=None):
        if not client_id or not client_secret.get_secret_value():raise ValueError('caller_client_required')
        self.config=config;self.client_id=client_id;self.secret=client_secret;self.send=send
        self.verifier=verifier or PlatformTokenVerifier(PlatformVerifierConfig(issuer=config.issuer,audience=config.audience,
            jwks_url=config.issuer+'/oidc/jwks',allow_loopback_http=config.allow_loopback_http))

    def exchange(self):
        c=self.config
        credentials=quote_plus(self.client_id)+':'+quote_plus(self.secret.get_secret_value())
        data=urlencode({'grant_type':GRANT,'audience':c.audience,'org_id':c.org_id,'workspace_id':c.workspace_id}).encode()
        reply=self.send(c.issuer+'/oidc/token',{'Authorization':'Basic '+base64.b64encode(credentials.encode()).decode(),
            'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'},data)
        if (reply.get('token_type')!='Bearer' or reply.get('issued_token_type')!='urn:ietf:params:oauth:token-type:access_token' or
            type(reply.get('expires_in')) is not int or not 0<reply['expires_in']<=300 or 'refresh_token' in reply):
            raise ValueError('service_exchange_response_rejected')
        token=reply.get('access_token');claims=ServiceTokens(self.verifier).verify(token,c.audience)
        if (claims['act']['sub'],claims['org_id'],claims['workspace_id'])!=(c.caller,c.org_id,c.workspace_id):
            raise ValueError('service_exchange_context_mismatch')
        return token

    def query(self,point,*,mode,max_age_s,accept_unverified_time=False):
        c=self.config
        query=Query(model_manifest_sha256=c.model_manifest_sha256,frame_id=c.frame_id,point_m=point,
            mode=mode,max_age_s=max_age_s,accept_unverified_time=accept_unverified_time)
        token=self.exchange()
        url=c.api_origin+f'/s2s/spaces/{c.space_id}/publications/{c.publication_id}/query'
        reply=self.send(url,{'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json'},
                        query.model_dump_json().encode())
        self.validate(reply,query)
        return reply

    def validate(self,reply,query):
        c=self.config
        expected={'profile':'cospace.online-consumption/0.1','space_id':c.space_id,'publication_id':c.publication_id,
            'model_id':c.model_id,'model_manifest_sha256':c.model_manifest_sha256,'source_model_sha256':c.source_model_sha256,
            'frame_id':c.frame_id,'grade':'unverified','robot_ready':False,'mode':query.mode,'lifecycle_state':'active'}
        if any(k not in reply or type(reply[k]) is not type(v) or reply[k]!=v for k,v in expected.items()):
            raise ValueError('consumer_response_binding_mismatch')
        if (reply.get('as_of','missing') is not None or reply.get('valid_until','missing') is not None or
            reply.get('freshness')!={'status':'unverified_clock','max_age_s':query.max_age_s,'observation_age_s':None}):
            raise ValueError('consumer_freshness_contract_mismatch')
        complete=reply.get('completeness',{})
        if (complete.get('requested')!=1 or complete.get('scope')!='requested_point_only' or complete.get('scene_coverage','missing') is not None):
            raise ValueError('consumer_completeness_contract_mismatch')
        if reply.get('status')=='refused':
            if reply.get('result') is not None or reply.get('refusal')!='observation_time_unverified' or complete.get('returned')!=0:
                raise ValueError('consumer_refusal_invalid')
            return
        if query.mode!='historical' or not query.accept_unverified_time or reply.get('status')!='historical_result' or reply.get('refusal') is not None:
            raise ValueError('consumer_operational_result_forbidden')
        result=reply.get('result',{})
        bindings={'model_id':c.model_id,'source_model_sha256':c.source_model_sha256,'frame_id':c.frame_id,'space_id':c.space_id,
                  'point_m':query.point_m,'quality':'unverified','robot_ready':False}
        if any(k not in result or type(result[k]) is not type(v) or result[k]!=v for k,v in bindings.items()):raise ValueError('consumer_result_binding_mismatch')
        if (result.get('state') not in ('surface_candidate','unknown') or complete.get('returned')!=1 or
            complete.get('unknown')!=int(result['state']=='unknown')):raise ValueError('consumer_unknown_contract_mismatch')
