"""Read-only fixed-version S2S consumption using Vxture RFC 8693 service tokens."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from packages.infrastructure.platform_identity import PlatformTokenVerifier,IdentityRejected,IdentityUnavailable
from packages.infrastructure.platform_identity import PlatformPrincipal
from packages.infrastructure.platform_subscription import SubscriptionDenied,SubscriptionUnavailable
from packages.lifecycle.preview_scope import match
from packages.service.preview_publications import PreviewPublications
from packages.service.public_errors import public_error


class ConsumerGrant(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    caller:str=Field(pattern=r'^[a-z][a-z0-9-]{0,99}$')
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')


class ConsumerConfig(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    profile:str=Field(pattern=r'^cospace\.online-consumer-access/0\.1$')
    audience:str=Field(pattern=r'^[a-z][a-z0-9-]{0,99}$')
    grants:list[ConsumerGrant]=Field(max_length=10000)


class Query(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    model_manifest_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    frame_id:str=Field(min_length=1,max_length=160)
    point_m:list[float]=Field(min_length=3,max_length=3)
    mode:str=Field(pattern=r'^(historical|operational)$')
    max_age_s:int=Field(ge=0,le=31536000)
    accept_unverified_time:bool=False


class ServiceTokens:
    def __init__(self,verifier):self.verifier=verifier

    def verify(self,token,audience):
        c=self.verifier.signed_claims(token);now=self.verifier.now()
        identifier=lambda v:isinstance(v,str) and bool(re.fullmatch('[A-Za-z0-9_-]{1,160}',v))
        if (c.get('aud')!=audience or c.get('mode')!='service' or c.get('scope')!='tool:'+audience or
            'sub' in c or 'delegated' in c or 'userType' in c or
            not isinstance(c.get('act'),dict) or set(c['act'])!={'sub'} or
            not isinstance(c['act']['sub'],str) or not re.fullmatch('[a-z][a-z0-9-]{0,99}',c['act']['sub']) or
            not identifier(c.get('org_id')) or not identifier(c.get('workspace_id')) or not identifier(c.get('jti')) or
            c['exp']<=now or c['iat']>now+30 or c.get('nbf',now)>now or c['exp']-c['iat']>300):
            raise IdentityRejected('service_token_rejected')
        return c


class OnlineConsumer:
    def __init__(self,rp,policies,jobs,config_path,*,verifier=None,subscriptions=None):
        self.rp=rp;self.policies=policies;self.jobs=jobs;self.path=Path(config_path)
        self.subscriptions=subscriptions
        config=self.load();self.audience=config.audience
        cfg=rp.config.verifier_config.model_copy(update={'audience':self.audience})
        self.tokens=ServiceTokens(verifier or PlatformTokenVerifier(cfg))

    def load(self):
        try:
            raw=self.path.read_bytes()
            if len(raw)>1024*1024:raise ValueError('consumer_config_budget')
            doc=ConsumerConfig.model_validate(json.loads(raw))
            keys=[(g.caller,g.space_id) for g in doc.grants]
            if len(keys)!=len(set(keys)):raise ValueError('duplicate_consumer_grant')
            return doc
        except (OSError,ValueError,TypeError) as exc:
            raise IdentityUnavailable('consumer_configuration_unavailable') from exc

    def query(self,space,publication,token,body):
        config=self.load()
        if config.audience!=self.audience:raise IdentityUnavailable('consumer_restart_required')
        claims=self.tokens.verify(token,config.audience)
        revision,policy=self.policies.load()
        binding=next((b for b in policy.bindings if b.space_id==space),None)
        if (binding is None or (binding.issuer,binding.org_id,binding.workspace_id)!=(claims['iss'],claims['org_id'],claims['workspace_id']) or
            not any(g.caller==claims['act']['sub'] and g.space_id==space for g in config.grants)):
            raise PermissionError('consumer_space_denied')
        principal=PlatformPrincipal(claims['iss'],'',claims['org_id'],claims['workspace_id'],(),'service',claims['exp'])
        if self.subscriptions is not None:self.subscriptions.require(principal)
        request=Query.model_validate(body)
        if not all(math.isfinite(v) for v in request.point_m):raise ValueError('consumer_point_invalid')
        pubs=PreviewPublications(self.jobs)
        # Authorize ownership before opening the publication geometry.
        metadata=json.loads((pubs.root/publication/'publication.json').read_bytes())
        if metadata.get('space_id')!=space:raise PermissionError('consumer_space_denied')
        status=pubs.require_distributing(publication)
        record,model=pubs.read(publication)
        match(record,{'space_id':space,'project_id':self.jobs.directory.read('space',space)['project_id']})
        if request.model_manifest_sha256!=record['model_manifest_sha256']:raise ValueError('consumer_version_mismatch')
        if request.frame_id!=model.manifest['frame_id']:raise ValueError('consumer_frame_mismatch')
        # Current supported recordings carry no verified UTC mapping. Build or
        # publication timestamps must never be substituted for observation time.
        response={'profile':'cospace.online-consumption/0.1','space_id':space,'publication_id':publication,
            'model_id':model.manifest['id'],'model_manifest_sha256':record['model_manifest_sha256'],
            'source_model_sha256':record['source_model_sha256'],'frame_id':model.manifest['frame_id'],
            'served_at':datetime.now(timezone.utc).isoformat(),'as_of':None,'valid_until':None,
            'freshness':{'status':'unverified_clock','max_age_s':request.max_age_s,'observation_age_s':None},
            'grade':'unverified','robot_ready':False,'mode':request.mode,'lifecycle_state':status['lifecycle_state'],
            'policy_revision':revision,'status':'refused','refusal':'observation_time_unverified',
            'completeness':{'requested':1,'returned':0,'unknown':0,'scope':'requested_point_only','scene_coverage':None},'result':None}
        if request.mode=='historical' and request.accept_unverified_time:
            result=model.query(request.point_m)
            response.update(status='historical_result',refusal=None,result=result,
                completeness={'requested':1,'returned':1,'unknown':int(result['state']=='unknown'),'scope':'requested_point_only','scene_coverage':None})
        # Recheck revocation and lifecycle immediately before handing out contents.
        current=self.load();_,current_policy=self.policies.load()
        if current!=config or current_policy!=policy:raise IdentityUnavailable('consumer_authorization_changed')
        pubs.require_distributing(publication)
        if self.subscriptions is not None:self.subscriptions.require(principal)
        return response

    async def dispatch(self,request):
        def deny(code,detail):return JSONResponse({'detail':detail},status_code=code,headers={'Cache-Control':'no-store'})
        route=re.fullmatch(r'/s2s/spaces/(space-[a-f0-9]{16})/publications/(preview-[a-f0-9]{16})/query',request.url.path)
        if not route or request.method!='POST' or request.query_params:return deny(404,'consumer_route_not_found')
        # Never fall back to browser cookies or accept dual credential sources.
        headers=request.headers.getlist('authorization')
        if len(headers)!=1 or not headers[0].startswith('Bearer ') or len(headers[0])>32775:return deny(401,'service_token_required')
        if request.headers.get('cookie') or request.headers.get('origin'):return deny(403,'service_credentials_only')
        if request.headers.get('content-type','').split(';')[0]!='application/json':return deny(415,'json_required')
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>8192:return deny(413,'consumer_request_budget')
        try:
            def unique(pairs):
                d={}
                for k,v in pairs:
                    if k in d:raise ValueError('duplicate_request_field')
                    d[k]=v
                return d
            body=json.loads(raw,object_pairs_hook=unique)
            value=await run_in_threadpool(self.query,route[1],route[2],headers[0][7:],body)
            return JSONResponse(value,headers={'Cache-Control':'no-store'})
        except IdentityRejected:return deny(401,'service_token_rejected')
        except SubscriptionDenied:return deny(403,'subscription_required')
        except SubscriptionUnavailable:return deny(503,'subscription_unavailable')
        except PermissionError:return deny(403,'consumer_space_denied')
        except FileNotFoundError:return deny(404,'consumer_publication_not_found')
        except (IdentityUnavailable,OSError,sqlite3.Error):return deny(503,'consumer_dependency_unavailable')
        except (ValidationError,ValueError,KeyError,TypeError,OverflowError) as exc:
            allowed=('publication_retired','publication_distribution_paused','consumer_version_mismatch','consumer_frame_mismatch')
            code=public_error(exc,allowed,'consumer_request_or_publication_invalid')
            return deny(422 if code=='consumer_request_or_publication_invalid' else 409,code)
