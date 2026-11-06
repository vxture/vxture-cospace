"""Vxture access-token verification for server-to-server use; not an RP login/session.

The RP keeps accounts login state. Expired access credentials reject this API call;
they never decide that the person's accounts login has ended.
"""
from dataclasses import dataclass
import json
import math
import re
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import RSAKey
from pydantic import BaseModel, ConfigDict, Field, model_validator


class IdentityRejected(ValueError):
    """Credential is invalid for this resource request (401, not global logout)."""


class IdentityUnavailable(RuntimeError):
    """Trusted key source is unavailable (503, never valid:false / logout)."""


class PlatformVerifierConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    issuer: str = Field(min_length=1, max_length=2048)
    audience: str = Field(min_length=1, max_length=256)
    jwks_url: str = Field(min_length=1, max_length=2048)
    allow_loopback_http: bool = False

    @model_validator(mode='after')
    def urls(self):
        for value in (self.issuer, self.jwks_url):
            parsed = urlsplit(value)
            local = self.allow_loopback_http and parsed.hostname in ('localhost', '127.0.0.1', '::1')
            if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and local)
                    or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query):
                raise ValueError('trusted_platform_url_required')
        if self.issuer.endswith('/'):
            raise ValueError('issuer_must_match_platform_exactly_without_trailing_slash')
        return self


@dataclass(frozen=True)
class PlatformPrincipal:
    issuer: str
    subject: str
    org_id: str
    workspace_id: str
    governance_roles: tuple[str, ...]
    display_name: str
    expires_at: int

    @property
    def workspace_owner(self):
        return 'workspace:owner' in self.governance_roles


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_jwks(url):
    # URL is explicit trusted server configuration, never a token jku/x5u value.
    with build_opener(NoRedirect()).open(Request(url, headers={'Accept': 'application/json'}), timeout=5) as response:
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise IdentityUnavailable('platform_keys_unavailable')
        return json.loads(raw)


class PlatformTokenVerifier:
    def __init__(self, config, fetch=fetch_jwks, now=time.time):
        self.config = config
        self.fetch, self.now = fetch, now
        self.keys, self.loaded_at, self.last_attempt = {}, None, None
        self.lock = threading.RLock()

    def _refresh(self):
        self.last_attempt = self.now()
        try:
            value = self.fetch(self.config.jwks_url)
            if not isinstance(value, dict) or not isinstance(value.get('keys'), list) or not 1 <= len(value['keys']) <= 64:
                raise ValueError('invalid_key_set')
            keys = {}
            for item in value['keys']:
                if not isinstance(item, dict):
                    raise ValueError('invalid_key')
                if item.get('kty') != 'RSA' or item.get('use', 'sig') != 'sig' or item.get('alg', 'RS256') != 'RS256':
                    continue
                kid = item.get('kid')
                if (not isinstance(kid, str) or not 1 <= len(kid) <= 256 or kid in keys
                        or any(k in item for k in ('d', 'p', 'q', 'dp', 'dq', 'qi', 'oth'))
                        or 'key_ops' in item and item['key_ops'] != ['verify']):
                    raise ValueError('invalid_verification_key')
                key = RSAKey.import_key(item)
                if key.raw_value.key_size < 2048:
                    raise ValueError('weak_verification_key')
                keys[kid] = key
            if not keys:
                raise ValueError('no_verification_key')
            self.keys, self.loaded_at = keys, self.now()
        except (OSError, ValueError, TypeError, KeyError, JoseError) as exc:
            raise IdentityUnavailable('platform_keys_unavailable') from exc

    def _key(self, obj):
        header = obj.headers()
        if (header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str)
                or not 1 <= len(header['kid']) <= 256
                or any(k in header for k in ('jku', 'jwk', 'x5u', 'x5c', 'crit'))):
            raise IdentityRejected('platform_credential_invalid')
        with self.lock:
            refreshed = False
            if self.loaded_at is None or self.now() - self.loaded_at >= 300:
                self._refresh(); refreshed = True
            kid = header['kid']
            # One refresh for rotation, with a short network backoff for random kid floods.
            if kid not in self.keys and not refreshed and self.now() - self.last_attempt >= 5:
                self._refresh()
            if kid not in self.keys:
                raise IdentityRejected('platform_credential_invalid')
            return self.keys[kid]

    def signed_claims(self, token):
        """Verify cryptography and issuer/audience/time; callers validate token kind."""
        if not isinstance(token, str) or not 1 <= len(token) <= 32_768:
            raise IdentityRejected('platform_credential_invalid')
        try:
            decoded = jwt.decode(token, self._key, algorithms=['RS256'])
            claims = decoded.claims
            jwt.JWTClaimsRegistry(now=self.now, leeway=60,
                iss={'essential': True, 'value': self.config.issuer},
                aud={'essential': True, 'value': self.config.audience},
                exp={'essential': True}, iat={'essential': True}).validate(claims)
            for name in ('exp', 'iat', 'nbf'):
                v = claims.get(name)
                if name in claims and (type(v) not in (int, float) or not math.isfinite(v)):
                    raise ValueError('invalid_numeric_date')
            if claims['exp'] <= self.now() - 60 or claims['exp'] <= claims['iat']:
                raise ValueError('invalid_validity')
            return claims
        except IdentityUnavailable:
            raise
        except (JoseError, ValueError, TypeError, KeyError, OverflowError) as exc:
            raise IdentityRejected('platform_credential_invalid') from exc

    def verified_claims(self, token):
        claims=self.signed_claims(token)
        if not isinstance(claims.get('sub'),str) or not re.fullmatch(r'usr_[A-Za-z0-9_-]{1,150}',claims['sub']):
            raise IdentityRejected('platform_credential_invalid')
        return claims

    def verify_id(self, token, *, nonce=None, subject=None, sid=None):
        claims = self.verified_claims(token)
        if (claims.get('userType') != 'tenant_user'
                or not isinstance(claims.get('sid'), str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', claims['sid'])
                or nonce is not None and claims.get('nonce') != nonce
                or subject is not None and claims['sub'] != subject
                or sid is not None and claims['sid'] != sid):
            raise IdentityRejected('platform_credential_invalid')
        audience = claims['aud']
        if (isinstance(audience, list) and len(audience) > 1 and claims.get('azp') != self.config.audience
                or 'azp' in claims and claims['azp'] != self.config.audience):
            raise IdentityRejected('platform_credential_invalid')
        return claims

    def verify(self, token):
        claims = self.verified_claims(token)
        try:
            if claims.get('userType') != 'tenant_user' or claims.get('account_status') != 'active':
                raise ValueError('active_tenant_account_required')
            for name in ('active_org', 'active_workspace'):
                if not isinstance(claims.get(name), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', claims[name]):
                    raise ValueError('explicit_tenant_context_required')
            roles = claims.get('roles')
            if not isinstance(roles, list) or len(roles) > 64 or any(not isinstance(r, str) or len(r) > 100 for r in roles):
                raise ValueError('invalid_governance_roles')
            known = {f'{scope}:{role}' for scope in ('org', 'workspace')
                     for role in ('owner', 'manager', 'member', 'readonly', 'guest')}
            # Preserve platform meanings; unknown/bare/admin values grant no authority.
            roles = tuple(sorted({r.strip().lower() for r in roles if r.strip().lower() in known}))
            name = claims.get('name') or claims.get('preferred_username') or claims['sub']
            if not isinstance(name, str) or len(name) > 500:
                name = claims['sub']
            return PlatformPrincipal(self.config.issuer, claims['sub'], claims['active_org'],
                                     claims['active_workspace'], roles, name, int(claims['exp']))
        except IdentityUnavailable:
            raise
        except (JoseError, ValueError, TypeError, KeyError, OverflowError) as exc:
            raise IdentityRejected('platform_credential_invalid') from exc
