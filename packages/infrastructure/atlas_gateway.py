"""Atlas data-plane client. Platform tickets and inference metering stay server-side."""
import ipaddress
import json
import os
import threading
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from pydantic import BaseModel, ConfigDict, Field, model_validator
from packages.infrastructure.platform_identity import (
    IdentityRejected, IdentityUnavailable, NoRedirect, PlatformTokenVerifier,
)


class AtlasUnavailable(RuntimeError): pass


def inference_error_code(error):
    """Map only Atlas's public code; vendor messages and account details stay private."""
    try:
        raw = error.read(8193)
        value = json.loads(raw) if len(raw) <= 8192 else None
        if isinstance(value, dict) and value.get('code') == 'UPSTREAM_ACCOUNT_REFUSED':
            return 'coordinate_ai_provider_account_unavailable'
    except (OSError, ValueError, TypeError):
        pass
    return ('coordinate_ai_rate_limited' if error.code == 429 else
            'coordinate_ai_access_denied' if error.code in (401, 403, 404) else 'coordinate_ai_unavailable')


class AtlasConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    base_url: str
    coordinate_endpoint: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_./-]{0,159}$')
    allow_tailnet_http: bool = False
    allow_loopback_http: bool = False

    @model_validator(mode='after')
    def origin(self):
        value = urlsplit(self.base_url)
        try:
            tailnet = ipaddress.ip_address(value.hostname or '') in ipaddress.ip_network('100.64.0.0/10')
        except ValueError:
            tailnet = False
        local = value.hostname in ('127.0.0.1', 'localhost', '::1')
        allowed = (value.scheme == 'https' or value.scheme == 'http' and
                   (tailnet and self.allow_tailnet_http or local and self.allow_loopback_http))
        if (not allowed or not value.hostname or value.username or value.password or value.path
                or value.query or value.fragment or any(c.isspace() for c in self.base_url)):
            raise ValueError('atlas_trusted_origin_required')
        return self


class AtlasGateway:
    def __init__(self, rp, config=None):
        self.rp, self.config = rp, config
        self.verifier = None
        self.slots = threading.BoundedSemaphore(2)

    @classmethod
    def from_env(cls, rp):
        base = os.environ.get('COSPACE_ATLAS_BASE_URL')
        route = os.environ.get('COSPACE_ATLAS_COORDINATE_ENDPOINT')
        config = AtlasConfig(base_url=base, coordinate_endpoint=route,
            allow_tailnet_http=os.environ.get('COSPACE_ATLAS_TAILNET_HTTP') == '1') if base and route else None
        return cls(rp, config)

    @property
    def available(self): return self.config is not None

    def token(self, principal, user_token):
        if not user_token or not principal.org_id or not principal.workspace_id:
            raise AtlasUnavailable('coordinate_ai_identity_unavailable')
        request = {'grant_type':'urn:ietf:params:oauth:grant-type:token-exchange', 'audience':'atlas',
            'requested_token_type':'urn:ietf:params:oauth:token-type:access_token',
            'subject_token':user_token, 'subject_token_type':'urn:ietf:params:oauth:token-type:access_token'}
        try:
            value = self.rp.transport.post('/oidc/token', request, form=True)
            if value.get('token_type') != 'Bearer': raise ValueError('token_type')
            bearer = value.get('access_token')
            if self.verifier is None:
                self.verifier = PlatformTokenVerifier(self.rp.config.verifier_config.model_copy(update={'audience':'atlas'}), now=self.rp.now)
            claims = self.verifier.signed_claims(bearer)
            now = self.rp.now()
            if (claims.get('aud') != 'atlas' or claims.get('act') != {'sub':'cospace'}
                    or claims.get('scope') != 'tool:atlas' or claims.get('mode') != 'obo'
                    or claims.get('delegated') is not None or claims.get('sub') != principal.subject
                    or (claims.get('org_id'), claims.get('workspace_id')) != (principal.org_id, principal.workspace_id)
                    or type(claims.get('iat')) is not int or type(claims.get('exp')) is not int
                    or claims['iat'] > now + 30 or claims['exp'] <= now or not 0 < claims['exp']-claims['iat'] <= 300):
                raise ValueError('atlas_ticket_binding')
            return bearer
        except (IdentityRejected, IdentityUnavailable, OSError, ValueError, TypeError, KeyError):
            raise AtlasUnavailable('coordinate_ai_identity_unavailable') from None

    def chat(self, principal, user_token, task_id, messages):
        if not self.available: raise AtlasUnavailable('coordinate_ai_unconfigured')
        if not self.slots.acquire(blocking=False): raise AtlasUnavailable('coordinate_ai_busy')
        try:
            bearer = self.token(principal, user_token)
            raw = json.dumps({'tenantId':principal.org_id,
                'taskId':task_id, 'endpointCode':self.config.coordinate_endpoint, 'messages':messages,
                'stream':False, 'thinking':'off', 'timeoutMs':45000, 'maxTokens':2048}, ensure_ascii=False).encode()
            self.check_route(bearer, raw, messages)
            request = Request(self.config.base_url+'/v1/chat', data=raw,
                headers={'Authorization':'Bearer '+bearer, 'Content-Type':'application/json', 'Accept':'application/json'})
            try:
                with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=50) as response:
                    raw = response.read(65_537)
                    if len(raw) > 65_536: raise ValueError('response_budget')
                    value = json.loads(raw)
                    if (not isinstance(value, dict) or not isinstance(value.get('message'), dict)
                            or not isinstance(value['message'].get('content'), str)
                            or value.get('finishReason') != 'stop' or value.get('thinking') != 'off'):
                        raise ValueError('response_shape')
                    return value['message']['content']
            except HTTPError as exc:
                raise AtlasUnavailable(inference_error_code(exc)) from None
            except (OSError, ValueError, TypeError):
                raise AtlasUnavailable('coordinate_ai_unavailable') from None
        finally:
            self.slots.release()

    def check_route(self, bearer, raw, messages):
        """Check the granted route before spending inference; never choose another route."""
        request = Request(self.config.base_url+'/v1/model-routes',
            headers={'Authorization':'Bearer '+bearer, 'Accept':'application/json'})
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5) as response:
                data = response.read(262_145)
                if len(data) > 262_144: raise ValueError('route_budget')
                value = json.loads(data)
            routes = value['endpoints']
            if not isinstance(routes, list): raise ValueError('route_shape')
            selected = [r for r in routes if isinstance(r, dict) and r.get('endpointCode') == self.config.coordinate_endpoint]
            if len(selected) != 1 or selected[0].get('state') != 'active' or selected[0].get('category') != 'chat':
                raise ValueError('route_unavailable')
            route = selected[0]
            # Conservative admission budget, not a token measurement. Unknown capacity is not unlimited.
            input_budget = sum(len(m['content'].encode())+32 for m in messages)
            if ('off' not in route.get('thinkingModes', [])
                    or type(value.get('maxRequestBytes')) is not int or len(raw) > value['maxRequestBytes']
                    or type(route.get('maxOutputTokens')) is not int or route['maxOutputTokens'] < 2048
                    or type(route.get('contextWindow')) is not int or route['contextWindow'] < input_budget+2048):
                raise ValueError('route_capacity')
        except (HTTPError, OSError, ValueError, TypeError, KeyError):
            raise AtlasUnavailable('coordinate_ai_route_unavailable') from None
