"""One accounts login authority, PKCE callback, durable refresh rotation."""
from dataclasses import asdict
import base64
import hashlib
import math
import re
import secrets
import time
from urllib.parse import urlencode
from packages.infrastructure.platform_identity import PlatformTokenVerifier, IdentityRejected, IdentityUnavailable
from packages.infrastructure.platform_rp import PlatformHttp, safe_return
from packages.infrastructure.platform_session_store import key_of

LOGIN_SCOPES = ('openid', 'profile', 'email')


def opaque(): return secrets.token_urlsafe(32)
def valid_opaque(value): return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{43}', value))


class PlatformLogin:
    def __init__(self, config, store, transport=None, verifier=None, now=time.time):
        self.config, self.store, self.now = config, store, now
        self.transport = transport or PlatformHttp(config)
        self.verifier = verifier or PlatformTokenVerifier(config.verifier_config, now=now)

    def begin(self, return_to, browser=None, *, select_account=False):
        return_to = safe_return(return_to)
        state, nonce, verifier = opaque(), opaque(), opaque()
        browser = browser if valid_opaque(browser) else opaque()
        self.store.put('state', state, {'browser': key_of(browser), 'nonce': nonce,
            'verifier': verifier, 'return_to': return_to, 'expires_at': self.now()+600,
            'issuer': self.config.issuer, 'client_id': self.config.client_id})
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        url = self.config.issuer+'/oidc/authorize?'+urlencode({
            'response_type': 'code', 'client_id': self.config.client_id, 'redirect_uri': self.config.callback,
            'scope': ' '.join(LOGIN_SCOPES), 'state': state, 'nonce': nonce,
            'code_challenge': challenge, 'code_challenge_method': 'S256',
            **({'prompt': 'select_account'} if select_account else {})})
        return url, browser

    def _tokens(self, tokens, *, nonce=None, prior=None):
        if not isinstance(tokens, dict) or tokens.get('token_type') != 'Bearer':
            raise IdentityRejected('invalid_token_response')
        access = tokens.get('access_token'); principal = self.verifier.verify(access)
        claims = self.verifier.verified_claims(access)
        sid = claims.get('sid')
        if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', sid):
            raise IdentityRejected('invalid_session_binding')
        if prior and (principal.subject != prior['principal']['subject'] or sid != prior['sid']):
            raise IdentityRejected('invalid_session_binding')
        id_token = tokens.get('id_token')
        if nonce is not None and not id_token: raise IdentityRejected('id_token_required')
        if id_token:
            identity = self.verifier.verify_id(id_token, nonce=nonce, subject=principal.subject, sid=sid)
            if 'at_hash' in identity:
                expected = base64.urlsafe_b64encode(hashlib.sha256(access.encode()).digest()[:16]).rstrip(b'=').decode()
                if identity['at_hash'] != expected: raise IdentityRejected('access_token_hash_mismatch')
        expires = tokens.get('expires_in')
        if type(expires) not in (int, float) or not math.isfinite(expires) or expires <= 0:
            raise IdentityRejected('invalid_token_response')
        refresh = tokens.get('refresh_token')
        if not isinstance(refresh, str) or not 1 <= len(refresh) <= 16384:
            raise IdentityRejected('rotated_refresh_token_required')
        return {'principal': asdict(principal), 'access_token': access, 'id_token': id_token or prior['id_token'],
            'refresh_token': refresh, 'access_expires_at': min(principal.expires_at, self.now()+expires),
            'sid': sid, 'refresh_pending': False, 'refresh_blocked': False}

    def complete(self, state, browser, code=None, error=None, old_session=None):
        if not valid_opaque(state) or not valid_opaque(browser): raise IdentityRejected('login_callback_rejected')
        pending = self.store.take_state(state, browser, self.now())
        if (not pending or error or not isinstance(code, str) or not 1 <= len(code) <= 4096
                or (pending['issuer'], pending['client_id']) != (self.config.issuer, self.config.client_id)):
            raise IdentityRejected('login_callback_rejected')
        session = self._tokens(self.transport.exchange(code, pending['verifier']), nonce=pending['nonce'])
        status = self.transport.status(session['sid'], True, self.now())
        if not status['valid']: raise IdentityRejected('accounts_session_ended')
        session.update(next_check_at=status['next_check_at'], retry_at=0, csrf=opaque(),
                       issuer=self.config.issuer, client_id=self.config.client_id)
        rpsid = opaque(); self.store.put('session', rpsid, session)
        # Session fixation defense. A successful re-login replaces this browser's session.
        if valid_opaque(old_session):
            with self.store.lock(old_session): self.store.delete('session', old_session)
        return rpsid, pending['return_to']

    def resolve(self, rpsid, *, active=False, require_access=False):
        if not valid_opaque(rpsid): return None, 'signed_out'
        with self.store.lock(rpsid):
            session = self.store.get('session', rpsid)
            if session is None: return None, 'signed_out'
            if (session.get('issuer'), session.get('client_id')) != (self.config.issuer, self.config.client_id):
                raise IdentityUnavailable('session_client_configuration_mismatch')
            state = 'unavailable' if session.get('retry_at', 0) else 'cached'
            if active and self.now() >= max(session['next_check_at'], session.get('retry_at', 0)):
                try:
                    status = self.transport.status(session['sid'], True, self.now())
                    if status['valid'] is False:
                        self.store.delete('session', rpsid); return None, 'signed_out'
                    session.update(next_check_at=status['next_check_at'], retry_at=0)
                    state = 'confirmed'
                except IdentityUnavailable:
                    # Retry schedule, never a login lifetime; retain encrypted session.
                    session['retry_at'] = self.now()+30; state = 'unavailable'
                self.store.put('session', rpsid, session)
            if require_access:
                if state == 'unavailable' or self.now() >= session['next_check_at']:
                    raise IdentityUnavailable('accounts_confirmation_required')
                if session['access_expires_at'] <= self.now()+60:
                    if session.get('refresh_pending') or session.get('refresh_blocked'):
                        raise IdentityUnavailable('grant_reauthorization_required')
                    # Commit BEFORE calling accounts. Crash/lost reply must never reuse a
                    # possibly consumed rotating refresh token after restart.
                    session['refresh_pending'] = True
                    self.store.put('session', rpsid, session)
                    try:
                        renewed = self._tokens(self.transport.refresh(session['refresh_token']), prior=session)
                    except (IdentityRejected, IdentityUnavailable):
                        session['refresh_blocked'] = True
                        self.store.put('session', rpsid, session)
                        raise IdentityUnavailable('grant_reauthorization_required') from None
                    session.update(renewed); self.store.put('session', rpsid, session)
                self.verifier.verify(session['access_token'])
            return session, state

    def csrf_matches(self, rpsid, value):
        if not valid_opaque(rpsid) or not valid_opaque(value): return False
        session = self.store.get('session', rpsid)
        return bool(session and secrets.compare_digest(session['csrf'], value))

    def logout(self, rpsid):
        if not valid_opaque(rpsid): raise IdentityRejected('session_required')
        with self.store.lock(rpsid):
            session = self.store.get('session', rpsid)
            if not session: raise IdentityRejected('session_required')
            url = self.config.issuer+'/oidc/end_session?'+urlencode({
                'id_token_hint': session['id_token'], 'client_id': self.config.client_id,
                'post_logout_redirect_uri': self.config.origin+'/', 'state': opaque()})
            self.store.delete('session', rpsid)
            return url
