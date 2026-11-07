"""Product usage facts sent to the platform; no prices, allowances or local wallet."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import stat
import threading
from types import SimpleNamespace
from urllib.request import Request, build_opener, ProxyHandler

from packages.infrastructure.platform_identity import IdentityUnavailable, NoRedirect
from packages.infrastructure.platform_subscription import EntitlementTransport, IDENTIFIER, PRODUCT, SubscriptionUnavailable, unique_json
from packages.lifecycle.preview_control_lock import mutation_guard

log=logging.getLogger(__name__)
MAX_SAFE_INTEGER=2**53-1


class UsageTransport(EntitlementTransport):
    def send(self, principal, method, path, body):
        try:
            if (principal.issuer!=self.rp.config.issuer
                    or any(not IDENTIFIER.fullmatch(getattr(principal,k)) for k in ('org_id','workspace_id'))):
                raise ValueError('usage_context_invalid')
            bearer=self.token(principal)
            request=Request(self.config.api_base+path,data=json.dumps(body,allow_nan=False).encode(),
                method=method,headers={'Authorization':'Bearer '+bearer,'Content-Type':'application/json','Accept':'application/json'})
            with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=5) as response:
                if response.status!=200:raise ValueError('usage_status')
                raw=response.read(1_048_577)
                if len(raw)>1_048_576:raise ValueError('usage_budget')
                value=unique_json(raw)
                if not isinstance(value,dict):raise ValueError('usage_object')
                return value
        except (IdentityUnavailable,OSError,ValueError,TypeError,KeyError):
            # Never echo provider bodies, tokens, URLs or workspace identifiers.
            raise SubscriptionUnavailable('platform_usage_unavailable') from None

    def gauge(self, principal, value, observed_at):
        if type(value) is not int or not 0<=value<=MAX_SAFE_INTEGER:
            raise ValueError('usage_gauge_value')
        stamp=datetime.fromisoformat(observed_at)
        if stamp.tzinfo is None:raise ValueError('usage_gauge_timestamp')
        body={'workspace_id':principal.workspace_id,'product':PRODUCT,'metric':'storage.bytes',
              'value':value,'observed_at':observed_at}
        result=self.send(principal,'PUT','/usage/gauge',body)
        if (result.get('workspace_id')!=principal.workspace_id or result.get('product')!=PRODUCT
                or result.get('metric')!='storage.bytes' or type(result.get('applied')) is not bool):
            raise SubscriptionUnavailable('platform_usage_response_invalid')
        # applied=False is a valid LWW response: a newer observation already won.
        return result

    def consume(self, principal, metric, amount, idempotency_key):
        """For an actual product-owned counter, once introduced in the platform.

        No current geometry operation invokes this. Atlas/Runos report their own
        calls; storage uses gauge. Retries must reuse the caller's persisted key.
        """
        if (not isinstance(metric,str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,99}',metric)
                or metric in ('storage.bytes','member.max','scene.max','ai.credit')
                or type(amount) is not int or not 0<amount<=MAX_SAFE_INTEGER
                or not isinstance(idempotency_key,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',idempotency_key)):
            raise ValueError('usage_counter_invalid')
        result=self.send(principal,'POST','/usage/consume',{'workspace_id':principal.workspace_id,
            'product':PRODUCT,'metric':metric,'amount':amount,'idempotency_key':idempotency_key,'intent':'report'})
        if 'gated' in result and type(result['gated']) is not bool:
            raise SubscriptionUnavailable('platform_usage_response_invalid')
        if result.get('gated') is not True and 'consumed' not in result:
            raise SubscriptionUnavailable('platform_usage_response_invalid')
        # gated is platform information, not a product exception or a local gate.
        return result


class StorageInventory:
    """Logical bytes of scene input payloads, retained builds and publications.

    One physical path is counted once within a Workspace. Files shared across
    Workspaces, links and foreign source paths are ambiguous, so skip the whole
    observation instead of inventing ownership or publishing a partial zero.
    Global metadata, fixtures, auth state, staging and container files are excluded.
    """
    def __init__(self, policies, inputs, jobs):
        self.policies,self.inputs,self.jobs=policies,inputs,jobs
        self.root=jobs.root.resolve().parent

    def snapshot(self):
        try:
            with mutation_guard(self.policies.path.parent), mutation_guard(self.root):
                _,policy=self.policies.load()
                scopes={};owners={};files={}
                for binding in policy.bindings:
                    scope=(binding.issuer,binding.org_id,binding.workspace_id)
                    scopes[binding.space_id]=scope;files.setdefault(scope,{})

                def add(path, owner):
                    path=Path(path)
                    if not path.is_absolute():raise ValueError('storage_absolute_path_required')
                    # Check every parent too; resolving alone would hide symlinks.
                    if (not path.is_relative_to(self.root) or '..' in path.parts
                            or not path.resolve().is_relative_to(self.root)):
                        raise ValueError('storage_foreign_path')
                    for part in (path,*path.parents):
                        if part==self.root.parent:break
                        if part.is_symlink() or part.is_junction():raise ValueError('storage_link')
                    info=path.stat()
                    if stat.S_ISDIR(info.st_mode):
                        for child in path.iterdir():add(child,owner)
                    elif stat.S_ISREG(info.st_mode):
                        key=str(path)
                        if key in owners and owners[key]!=owner:raise ValueError('storage_shared_workspace_file')
                        owners[key]=owner;files[owner][key]=info.st_size
                    else:raise ValueError('storage_special_file')

                for path in sorted(self.inputs.root.glob('input-*.json')):
                    record=self.inputs.read_original(path.stem);owner=scopes.get(record.get('space_id'))
                    if owner is None:continue
                    add(record['snapshot'],owner)
                    if record.get('tracking'):add(record['tracking'],owner)
                from packages.data.scene_attachments import stored_records
                for folder,record in stored_records(self.inputs.root,verify=True):
                    owner=scopes.get(record.get('space_id'))
                    if owner is None:continue
                    add(folder,owner)
                for pattern in ('build-*/job.json','publications/preview-*/publication.json'):
                    for path in sorted(self.jobs.root.glob(pattern)):
                        record=json.loads(path.read_bytes());owner=scopes.get(record.get('space_id'))
                        if owner is not None:add(path.parent,owner)
                observed_at=datetime.now(timezone.utc).isoformat()
                result=[]
                for (issuer,org_id,workspace_id),members in files.items():
                    total=sum(members.values())
                    if total>MAX_SAFE_INTEGER:raise ValueError('storage_integer_budget')
                    result.append((SimpleNamespace(issuer=issuer,org_id=org_id,workspace_id=workspace_id),total,observed_at))
                return result
        except (IdentityUnavailable,OSError,ValueError,TypeError,KeyError,RecursionError):
            raise SubscriptionUnavailable('storage_observation_unavailable') from None


class StorageReporter:
    def __init__(self, inventory, transport, *, interval=300):
        if not 30<=interval<=3600:raise ValueError('usage_interval_invalid')
        self.inventory,self.transport,self.interval=inventory,transport,interval
        self.lock=threading.Lock();self.stop=threading.Event()

    def run_once(self):
        with self.lock:
            observations=self.inventory.snapshot();reported=failed=0
            for principal,value,stamp in observations:
                if self.stop.is_set():break
                try:self.transport.gauge(principal,value,stamp);reported+=1
                except SubscriptionUnavailable:failed+=1
            if failed:raise SubscriptionUnavailable('platform_usage_retry_scheduled')
            return reported

    @asynccontextmanager
    async def lifespan(self, app):
        self.stop.clear()
        async def poll():
            while not self.stop.is_set():
                try:
                    count=await asyncio.to_thread(self.run_once)
                    log.info('CoSpace storage observations reported=%d',count)
                except SubscriptionUnavailable:
                    log.warning('CoSpace storage reporting unavailable; retry scheduled')
                await asyncio.sleep(self.interval)
        task=asyncio.create_task(poll())
        try:yield
        finally:
            self.stop.set();task.cancel()
            with suppress(asyncio.CancelledError):await task
