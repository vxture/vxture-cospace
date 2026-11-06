"""Platform OIDC transport/configuration. Tokens and secrets stay on the server."""
import base64
import json
import math
import os
from urllib.error import HTTPError
from urllib.parse import urlencode, quote_plus, urlsplit, unquote
from urllib.request import Request, build_opener, ProxyHandler
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator
from packages.infrastructure.platform_identity import PlatformVerifierConfig, NoRedirect, IdentityUnavailable


def safe_return(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('invalid_return_path')
    decoded = value
    for _ in range(3): decoded = unquote(decoded)
    parsed = urlsplit(decoded)
    if (not decoded.startswith('/workbench/') or decoded.startswith('//') or parsed.scheme or parsed.netloc
            or '\\' in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
            or '..' in parsed.path.split('/')):
        raise ValueError('invalid_return_path')
    return value


class RpConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    issuer: str = 'https://accounts.vxture.com'
    backchannel: str = 'https://accounts.vxture.com'
    client_id: str
    client_secret: SecretStr
    origin: str
    encryption_key: SecretStr
    allow_loopback_http: bool = False

    @model_validator(mode='after')
    def validate_endpoints(self):
        for value in (self.issuer, self.backchannel, self.origin):
            PlatformVerifierConfig(issuer=value, audience=self.client_id, jwks_url=value+'/oidc/jwks',
                                   allow_loopback_http=self.allow_loopback_http)
        if urlsplit(self.origin).path or not self.client_id or len(self.client_id) > 256:
            raise ValueError('rp_origin_and_client_required')
        if not self.client_secret.get_secret_value(): raise ValueError('rp_client_secret_required')
        from cryptography.fernet import Fernet
        Fernet(self.encryption_key.get_secret_value().encode())
        return self

    @property
    def cookie_name(self):
        return '__Host-cospace_rp' if self.origin.startswith('https://') else 'cospace_rp'

    @property
    def callback(self): return self.origin+'/auth/callback'

    @property
    def verifier_config(self):
        return PlatformVerifierConfig(issuer=self.issuer, audience=self.client_id,
            jwks_url=self.backchannel+'/oidc/jwks', allow_loopback_http=self.allow_loopback_http)

    @classmethod
    def from_env(cls):
        required = ('COSPACE_OIDC_CLIENT_ID', 'COSPACE_OIDC_CLIENT_SECRET', 'COSPACE_ORIGIN', 'COSPACE_SESSION_KEY')
        if any(not os.environ.get(n) for n in required): raise ValueError('rp_configuration_incomplete')
        issuer = os.environ.get('COSPACE_OIDC_ISSUER', 'https://accounts.vxture.com')
        return cls(issuer=issuer, backchannel=os.environ.get('COSPACE_OIDC_BACKCHANNEL', issuer),
            client_id=os.environ[required[0]], client_secret=SecretStr(os.environ[required[1]]),
            origin=os.environ[required[2]], encryption_key=SecretStr(os.environ[required[3]]),
            allow_loopback_http=os.environ.get('COSPACE_OIDC_LOOPBACK_HTTP') == '1')


class PlatformHttp:
    def __init__(self, config): self.config = config

    def post(self, path, body, *, form=False):
        cfg = self.config
        credentials = quote_plus(cfg.client_id)+':'+quote_plus(cfg.client_secret.get_secret_value())
        raw = (urlencode(body) if form else json.dumps(body)).encode()
        request = Request(cfg.backchannel+path, data=raw, headers={
            'Authorization': 'Basic '+base64.b64encode(credentials.encode()).decode(),
            'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json',
            'Accept': 'application/json'}, method='POST')
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5) as response:
                result = response.read(1_048_577)
                if len(result) > 1_048_576: raise ValueError('response_too_large')
                value = json.loads(result)
                if not isinstance(value, dict): raise ValueError('response_not_object')
                return value
        except (HTTPError, OSError, ValueError) as exc:
            # Never log token endpoint bodies, credentials or individual tokens.
            raise IdentityUnavailable('platform_request_unavailable') from exc

    def exchange(self, code, verifier):
        return self.post('/oidc/token', {'grant_type': 'authorization_code', 'code': code,
            'redirect_uri': self.config.callback, 'code_verifier': verifier}, form=True)

    def refresh(self, token):
        return self.post('/oidc/token', {'grant_type': 'refresh_token', 'refresh_token': token}, form=True)

    def status(self, sid, active, now):
        result = self.post('/oidc/session/status', {'sid': sid, 'active': active})
        if set(result) == {'valid'} and result['valid'] is False: return result
        deadline = result.get('next_check_at')
        if (set(result) != {'valid', 'next_check_at'} or result['valid'] is not True
                or type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline < now):
            raise IdentityUnavailable('platform_status_unavailable')
        return result
