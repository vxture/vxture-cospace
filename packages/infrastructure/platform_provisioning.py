"""Read-only platform reconciliation; no member, price, quota or workspace master copy."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime
import logging
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

from packages.infrastructure.platform_identity import IdentityRejected, IdentityUnavailable, NoRedirect, PlatformTokenVerifier
from packages.infrastructure.platform_subscription import PRODUCT, IDENTIFIER, SubscriptionUnavailable, unique_json

log=logging.getLogger(__name__)


class ProvisioningTransport:
    def __init__(self, rp, config):
        self.rp,self.config=rp,config
        self.verifier=PlatformTokenVerifier(rp.config.verifier_config.model_copy(update={'audience':'vxture'}))
        self.bearer=None;self.expires_at=0

    def token(self):
        if self.bearer and self.expires_at>time.time()+10:return self.bearer
        result=self.rp.transport.post('/oidc/token',{
            'grant_type':'urn:ietf:params:oauth:grant-type:token-exchange',
            'audience':'vxture','scope':'provisioning:read'},form=True)
        if result.get('token_type')!='Bearer':raise ValueError('provisioning_token_type')
        bearer=result.get('access_token');claims=self.verifier.signed_claims(bearer)
        if (claims.get('aud')!='vxture' or claims.get('act')!={'sub':PRODUCT}
                or claims.get('scope')!='provisioning:read' or claims.get('mode')!='service'
                or any(k in claims for k in ('sub','workspace_id','org_id','tenant_id','delegated'))
                or claims.get('exp',0)<=time.time() or claims['exp']-claims['iat']>300):
            raise ValueError('provisioning_token_binding')
        self.bearer,self.expires_at=bearer,claims['exp']
        return bearer

    def page(self, cursor=None):
        try:
            query={'limit':200}
            if cursor is not None:query['cursor']=cursor
            url=self.config.api_base+'/platform/provisioning?'+urlencode(query)
            for attempt in range(2):
                bearer=self.token()
                try:
                    request=Request(url,headers={'Authorization':'Bearer '+bearer,'Accept':'application/json'})
                    with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=5) as response:
                        if response.status!=200:raise ValueError('provisioning_response_status')
                        raw=response.read(1_048_577)
                        if len(raw)>1_048_576:raise ValueError('provisioning_response_budget')
                        return unique_json(raw)
                except HTTPError as exc:
                    exc.close()
                    if exc.code!=401 or attempt:raise
                    self.bearer=None;self.expires_at=0
        except (IdentityRejected,IdentityUnavailable,OSError,ValueError,TypeError,KeyError):
            raise SubscriptionUnavailable('platform_provisioning_unavailable') from None


def validated_page(value):
    if (not isinstance(value,dict) or not isinstance(value.get('items'),list)
            or len(value['items'])>200 or 'nextCursor' not in value):
        raise SubscriptionUnavailable('provisioning_invalid_page')
    cursor=value['nextCursor']
    if cursor is not None and (not isinstance(cursor,str) or not 1<=len(cursor)<=512
                               or not cursor.isascii() or any(c.isspace() for c in cursor)):
        raise SubscriptionUnavailable('provisioning_invalid_cursor')
    for item in value['items']:
        if (not isinstance(item,dict)
                or any(not isinstance(item.get(k),str) or not IDENTIFIER.fullmatch(item[k]) for k in ('workspace_id','tenant_id'))
                or item.get('state') not in ('pending','provisioned','deprovisioned')
                or type(item.get('seq')) is not int or not 0<=item['seq']<=2**53-1
                or not isinstance(item.get('updated_at'),str)):
            raise SubscriptionUnavailable('provisioning_invalid_item')
        try:
            stamp=datetime.fromisoformat(item['updated_at'])
            if stamp.tzinfo is None:raise ValueError()
        except ValueError:raise SubscriptionUnavailable('provisioning_invalid_timestamp') from None
    return value['items'],cursor


class ProvisioningReconciler:
    def __init__(self, subscriptions, *, page=None, interval=300):
        if not 30<=interval<=3600:raise ValueError('provisioning_interval_invalid')
        self.subscriptions=subscriptions
        self.page=page or ProvisioningTransport(subscriptions.rp,subscriptions.config).page
        self.interval=interval;self.lock=threading.Lock();self.stop=threading.Event()

    def run_once(self):
        # Each round starts from the beginning. A missing row never means deletion.
        with self.lock:
            cursor=None;seen=set();pages=scanned=applied=0
            while not self.stop.is_set():
                items,next_cursor=validated_page(self.page(cursor))
                for item in items:
                    applied+=self.subscriptions.events.reconcile(item)
                pages+=1;scanned+=len(items)
                if next_cursor is None:
                    return {'pages':pages,'scanned':scanned,'applied':applied}
                if next_cursor in seen or pages>=1000:
                    raise SubscriptionUnavailable('provisioning_cursor_loop')
                seen.add(next_cursor);cursor=next_cursor
            raise SubscriptionUnavailable('provisioning_stopped')

    @asynccontextmanager
    async def lifespan(self, app):
        self.stop.clear()
        async def poll():
            while not self.stop.is_set():
                try:
                    result=await asyncio.to_thread(self.run_once)
                    log.info('CoSpace provisioning reconciliation pages=%d scanned=%d applied=%d',
                        result['pages'],result['scanned'],result['applied'])
                except SubscriptionUnavailable:
                    # No token bodies, IDs or provider error contents in logs.
                    log.warning('CoSpace provisioning reconciliation unavailable; retry scheduled')
                await asyncio.sleep(self.interval)
        task=asyncio.create_task(poll())
        try:yield
        finally:
            self.stop.set();task.cancel()
            with suppress(asyncio.CancelledError):await task
