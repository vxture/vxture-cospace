"""Vxture C2 facts in short memory cache; C3 receipts contain no entitlements or secrets."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from packages.infrastructure.platform_identity import IdentityUnavailable, IdentityRejected, NoRedirect, PlatformTokenVerifier

PRODUCT='cospace'
EVENTS={'tenant.provisioned','tenant.deprovisioned','subscription_changed','grant.invalidated'}
TIERS={'free','starter','pro','business','enterprise'}
STATUSES={'active','expiring','trialing','overdue','suspended','expired','cancelled'}
IDENTIFIER=re.compile(r'^[A-Za-z0-9_-]{1,160}$')


class SubscriptionDenied(PermissionError): pass
class ApplicationAccessDenied(SubscriptionDenied): pass
class SubscriptionUnavailable(IdentityUnavailable): pass
class WebhookRejected(ValueError): pass
class WebhookConflict(ValueError): pass


class SubscriptionConfig(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    api_base:str
    website_base:str='https://vxture.com'
    cache_seconds:int=Field(default=30,ge=0,le=45)
    webhook_keys:tuple[SecretStr,...]=Field(min_length=1,max_length=2)
    allow_tailnet_http:bool=False
    allow_loopback_http:bool=False

    @model_validator(mode='after')
    def trusted(self):
        website=urlsplit(self.website_base)
        if (website.scheme!='https' or not website.hostname or website.username or website.password
                or website.path or website.query or website.fragment
                or any(c.isspace() for c in self.website_base)):
            raise ValueError('trusted_website_origin_required')
        p=urlsplit(self.api_base)
        tailnet=False
        try:tailnet=ipaddress.ip_address(p.hostname or '') in ipaddress.ip_network('100.64.0.0/10')
        except ValueError:pass
        local=p.hostname in ('127.0.0.1','localhost','::1')
        permitted=p.scheme=='https' or p.scheme=='http' and (tailnet and self.allow_tailnet_http or local and self.allow_loopback_http)
        if (not permitted or not p.hostname or p.username or p.password or p.path or p.query or p.fragment
                or any(len(key.get_secret_value())<32 for key in self.webhook_keys)):
            raise ValueError('trusted_subscription_configuration_required')
        return self

    @classmethod
    def from_env(cls):
        names=('COSPACE_PLATFORM_API_URL','COSPACE_PLATFORM_WEBHOOK_SECRET')
        if any(not os.environ.get(n) for n in names):raise ValueError('subscription_configuration_required')
        keys=[os.environ[names[1]]]
        if os.environ.get('COSPACE_PLATFORM_WEBHOOK_PREVIOUS_SECRET'):keys.append(os.environ['COSPACE_PLATFORM_WEBHOOK_PREVIOUS_SECRET'])
        return cls(api_base=os.environ[names[0]],website_base=os.environ.get('COSPACE_WEBSITE_BASE_URL','https://vxture.com'),
            webhook_keys=tuple(SecretStr(v) for v in keys),
            allow_tailnet_http=os.environ.get('COSPACE_PLATFORM_TAILNET_HTTP')=='1')


class Entitlement(BaseModel):
    # Platform may add fields. Unknown decision values are retained but never grant access.
    model_config=ConfigDict(extra='ignore',strict=True,allow_inf_nan=False,frozen=True)
    workspace_id:str
    product:str
    status:str|None
    tier:str|None
    bundled:bool
    limits:dict[str,float]
    quota_pools:list[dict]
    trial_ends_at:str|None=None
    current_period_end:str|None=None
    cancel_at_period_end:bool=False
    data_retention_until:str|None=None

    def allowed(self,*,ui=False):
        return ((self.status is None or self.status in STATUSES)
            and (self.tier is None or self.tier in TIERS)
            and (self.tier is not None or not ui and self.bundled))


def unique_json(raw):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ValueError('duplicate_json_key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('json_number')))


class SubscriptionEvents:
    """Durable receipt deduplication + generation fence; never copies C2 entitlement facts."""
    def __init__(self,root):
        self.path=Path(root)/'platform-events.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(self.connect()) as db:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,digest TEXT,workspace TEXT,event TEXT,seq INTEGER,received_at TEXT)')
                db.execute('CREATE TABLE IF NOT EXISTS generations(workspace TEXT PRIMARY KEY,generation INTEGER,seq INTEGER)')
                db.execute('CREATE TABLE IF NOT EXISTS provisioning_refs(workspace TEXT PRIMARY KEY,tenant TEXT NOT NULL,state TEXT NOT NULL,seq INTEGER NOT NULL)')

    def connect(self):return sqlite3.connect(self.path,timeout=10)

    def generation(self,workspace):
        try:
            with closing(self.connect()) as db:
                row=db.execute('SELECT generation FROM generations WHERE workspace=?',(workspace,)).fetchone()
                return row[0] if row else 0
        except (OSError,sqlite3.Error) as exc:raise SubscriptionUnavailable('subscription_receipts_unavailable') from exc

    def accept(self,event,raw):
        digest=hashlib.sha256(raw).hexdigest();workspace=event['workspace_id'];seq=event.get('seq')
        try:
            with closing(self.connect()) as db:
                with db:
                    db.execute('BEGIN IMMEDIATE')
                    old=db.execute('SELECT digest FROM receipts WHERE id=?',(event['id'],)).fetchone()
                    if old:
                        if old[0]!=digest:raise WebhookConflict('webhook_id_payload_conflict')
                        return {'received':True,'replayed':True,'ignored_stale':False}
                    previous=db.execute('SELECT generation,seq FROM generations WHERE workspace=?',(workspace,)).fetchone()
                    generation,last=previous if previous else (0,-1)
                    stale=seq is not None and seq<=last
                    db.execute('INSERT INTO receipts VALUES(?,?,?,?,?,?)',(event['id'],digest,workspace,event['type'],seq,
                        datetime.now(timezone.utc).isoformat()))
                    if not stale:
                        db.execute('INSERT OR REPLACE INTO generations VALUES(?,?,?)',(workspace,generation+1,seq if seq is not None else last))
                        if seq is not None:
                            db.execute('INSERT OR REPLACE INTO provisioning_refs VALUES(?,?,?,?)',
                                (workspace,event['tenant_id'],event['type'].removeprefix('tenant.'),seq))
                    return {'received':True,'replayed':False,'ignored_stale':stale}
        except (OSError,sqlite3.Error) as exc:raise SubscriptionUnavailable('subscription_receipts_unavailable') from exc

    def reconcile(self, item):
        """Retain only platform lifecycle references, never a local entitlement decision."""
        if item['state']=='pending':return False
        try:
            with closing(self.connect()) as db, db:
                db.execute('BEGIN IMMEDIATE')
                workspace=item['workspace_id'];seq=item['seq']
                old=db.execute('SELECT generation,seq FROM generations WHERE workspace=?',(workspace,)).fetchone()
                generation,last=old if old else (0,-1)
                if seq<last:return False
                ref=db.execute('SELECT tenant,state,seq FROM provisioning_refs WHERE workspace=?',(workspace,)).fetchone()
                if seq==last and ref is not None:
                    if ref!=(item['tenant_id'],item['state'],seq):
                        raise SubscriptionUnavailable('provisioning_sequence_conflict')
                    return False
                db.execute('INSERT OR REPLACE INTO provisioning_refs VALUES(?,?,?,?)',
                    (workspace,item['tenant_id'],item['state'],seq))
                db.execute('INSERT OR REPLACE INTO generations VALUES(?,?,?)',(workspace,generation+1,seq))
                return True
        except (OSError,sqlite3.Error) as exc:raise SubscriptionUnavailable('subscription_receipts_unavailable') from exc


class EntitlementTransport:
    def __init__(self,rp,config):
        self.rp,self.config=rp,config
        self.verifier=PlatformTokenVerifier(rp.config.verifier_config.model_copy(update={'audience':'vxture'}))

    def token(self,principal,user_token=None):
        request={'grant_type':'urn:ietf:params:oauth:grant-type:token-exchange','audience':'vxture',
            'requested_token_type':'urn:ietf:params:oauth:token-type:access_token'}
        if user_token:
            request.update(subject_token=user_token,subject_token_type='urn:ietf:params:oauth:token-type:access_token')
        else:request.update(org_id=principal.org_id,workspace_id=principal.workspace_id)
        try:
            token=self.rp.transport.post('/oidc/token',request,form=True)
            if token.get('token_type')!='Bearer':raise ValueError('token_type')
            bearer=token.get('access_token');claims=self.verifier.signed_claims(bearer)
            if (claims.get('aud')!='vxture' or claims.get('act')!={'sub':PRODUCT}
                    or claims.get('scope')!='tool:vxture' or claims.get('delegated') is not None
                    or claims.get('mode')!=('obo' if user_token else 'service')
                    or (claims.get('org_id'),claims.get('workspace_id'))!=(principal.org_id,principal.workspace_id)
                    or claims.get('exp',0)<=time.time() or claims['exp']-claims['iat']>300
                    or user_token and claims.get('sub')!=principal.subject or not user_token and 'sub' in claims):
                raise ValueError('subscription_token_binding')
            return bearer
        except (IdentityRejected,IdentityUnavailable,OSError,ValueError,TypeError,KeyError):
            raise SubscriptionUnavailable('platform_subscription_unavailable') from None

    def fetch(self,principal,user_token=None):
        try:
            bearer=self.token(principal,user_token)
            url=self.config.api_base+'/platform/entitlements?'+urlencode({'workspace_id':principal.workspace_id,'product':PRODUCT})
            opener=build_opener(ProxyHandler({}),NoRedirect())
            with opener.open(Request(url,headers={'Authorization':'Bearer '+bearer,'Accept':'application/json'}),timeout=5) as response:
                if response.status!=200:raise ValueError('subscription_response_status')
                raw=response.read(1_048_577)
                if len(raw)>1_048_576:raise ValueError('subscription_response_budget')
                return unique_json(raw)
        except (IdentityRejected,IdentityUnavailable,OSError,ValueError,TypeError,KeyError) as exc:
            raise SubscriptionUnavailable('platform_subscription_unavailable') from None

    def access(self, principal, user_token):
        if not user_token: raise SubscriptionUnavailable('user_bound_access_required')
        try:
            bearer = self.token(principal, user_token)
            opener = build_opener(ProxyHandler({}), NoRedirect())
            request = Request(self.config.api_base+'/platform/product-access',
                headers={'Authorization': 'Bearer '+bearer, 'Accept': 'application/json'})
            with opener.open(request, timeout=5) as response:
                if response.status != 200: raise ValueError('access_response_status')
                raw = response.read(16385)
                if len(raw) > 16384: raise ValueError('access_response_budget')
                return unique_json(raw)
        except (IdentityRejected, IdentityUnavailable, OSError, ValueError, TypeError, KeyError):
            raise SubscriptionUnavailable('platform_application_access_unavailable') from None


class PlatformSubscriptions:
    def __init__(self,rp,config,root,*,fetch=None,fetch_access=None,now=time.monotonic,wall=time.time):
        if rp.config.client_id!=PRODUCT:raise ValueError('cospace_subscription_client_required')
        self.rp,self.config=rp,config;self.events=SubscriptionEvents(root)
        self.fetch=fetch or EntitlementTransport(rp,config).fetch
        self.fetch_access=fetch_access or (lambda principal, token: EntitlementTransport(rp,config).access(principal, token))
        self.now,self.wall=now,wall;self.cache={};self.lock=threading.RLock()

    def view(self,principal,user_token=None):
        if principal.issuer!=self.rp.config.issuer or not IDENTIFIER.fullmatch(principal.workspace_id):
            raise SubscriptionUnavailable('subscription_context_invalid')
        key=(principal.issuer,principal.org_id,principal.workspace_id)
        try:
            with self.lock:
                generation=self.events.generation(principal.workspace_id);cached=self.cache.get(key)
                if cached and cached[0]>self.now() and cached[1]==generation:return cached[2]
                # No stale fallback after expiry or a signed invalidation.
                value=Entitlement.model_validate(self.fetch(principal,user_token))
                if value.workspace_id!=principal.workspace_id or value.product!=PRODUCT:
                    raise ValueError('subscription_response_scope_mismatch')
                if self.events.generation(principal.workspace_id)!=generation:
                    raise SubscriptionUnavailable('subscription_changed_during_read')
                self.cache[key]=(self.now()+self.config.cache_seconds,generation,value)
                # Bound a single-worker memory cache; eviction merely causes a fresh C2 read.
                if len(self.cache)>512:self.cache.pop(next(iter(self.cache)))
                return value
        except SubscriptionUnavailable:raise
        except (ValueError,TypeError,KeyError,OSError,sqlite3.Error) as exc:
            raise SubscriptionUnavailable('platform_subscription_unavailable') from None

    def assigned(self, principal, user_token):
        # Never reuse a workspace entitlement cache as user authorization. A
        # revocation must affect the next request, including an existing session.
        try:
            value = self.fetch_access(principal, user_token)
            if (not isinstance(value, dict) or type(value.get('allowed')) is not bool
                    or (value.get('product'), value.get('subject'), value.get('org_id'), value.get('workspace_id'))
                    != (PRODUCT, principal.subject, principal.org_id, principal.workspace_id)):
                raise ValueError('application_access_scope_mismatch')
            return value['allowed']
        except SubscriptionUnavailable: raise
        except (ValueError, TypeError, KeyError, OSError):
            raise SubscriptionUnavailable('platform_application_access_unavailable') from None

    def require(self,principal,user_token=None,*,ui=False):
        value=self.view(principal,user_token)
        if not value.allowed(ui=ui):raise SubscriptionDenied('subscription_required')
        if user_token and not self.assigned(principal,user_token):raise ApplicationAccessDenied('application_access_required')
        return value

    def summary(self,principal,user_token=None):
        value=self.view(principal,user_token)
        assigned = self.assigned(principal,user_token) if user_token and value.allowed() else None
        permitted = assigned is not False
        return {'profile':'cospace.subscription-access/0.1','product':PRODUCT,
            'application_authorized':assigned,
            'access_reason':'application_access_required' if assigned is False else None,
            'status':value.status,'tier':value.tier,'bundled':value.bundled,
            'business_allowed':value.allowed(ui=True) and permitted,'data_allowed':value.allowed() and permitted,'ui_available':value.allowed(ui=True) and permitted,
            'pricing_url':self.config.website_base+'/pricing?'+urlencode({'product':PRODUCT}),
            'cache_max_age_s':self.config.cache_seconds}

    def webhook(self,raw,headers):
        if not 0<len(raw)<=65536:raise WebhookRejected('webhook_budget')
        if len(headers.getlist('x-vxture-signature'))!=1:raise WebhookRejected('webhook_header')
        signature=headers['x-vxture-signature']
        fields={}
        for part in signature.split(','):
            pair=part.strip().split('=',1)
            if len(pair)!=2 or pair[0] in fields:raise WebhookRejected('webhook_signature')
            fields[pair[0]]=pair[1]
        if (set(fields)!={'t','v1'} or not re.fullmatch(r'[0-9]{1,12}',fields['t'])
                or not re.fullmatch(r'[a-f0-9]{64}',fields['v1'])
                or abs(self.wall()-int(fields['t']))>300):raise WebhookRejected('webhook_signature')
        signed=fields['t'].encode()+b'.'+raw
        if not any(hmac.compare_digest(hmac.new(key.get_secret_value().encode(),signed,hashlib.sha256).hexdigest(),fields['v1']) for key in self.config.webhook_keys):
            raise WebhookRejected('webhook_signature')
        try:
            value=unique_json(raw)
            if not isinstance(value,dict):raise ValueError('webhook_object')
            for name in ('id','workspace_id','tenant_id'):
                if not isinstance(value.get(name),str) or not IDENTIFIER.fullmatch(value[name]):raise ValueError('webhook_scope')
            if (value.get('application')!=PRODUCT or value.get('type') not in EVENTS
                    or type(value.get('occurred_at')) not in (int,float) or not math.isfinite(value['occurred_at'])
                    or not 0<value['occurred_at']<=self.wall()+300 or not isinstance(value.get('data'),dict)):
                raise ValueError('webhook_envelope')
            if value['type'].startswith('tenant.'):
                if type(value.get('seq')) is not int or value['seq']<0:raise ValueError('webhook_sequence')
            elif 'seq' in value:raise ValueError('webhook_sequence')
        except (ValueError,TypeError,KeyError) as exc:raise WebhookRejected('webhook_payload') from None
        # The receipt invalidates commercial facts. It never grants a scene role,
        # creates a fake org/workspace binding, or deletes historical artifacts.
        return self.events.accept(value,raw)
