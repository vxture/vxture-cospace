"""Injectable local host identity; no user identity is inferred from request data."""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

PROFILE = 'vxture.ontology-local-host/0.1'
PERMISSIONS = frozenset({'read', 'read_private', 'edit', 'submit', 'review', 'publish', 'configure_groups'})
_IDENTITY = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}')
_TOKEN = re.compile(r'[a-zA-Z0-9_-]{43}')
_DIGEST = re.compile(r'[a-f0-9]{64}')
_MAX_CONFIG = 64 * 1024


def strict_json(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate_key')
            result[key] = value
        return result

    def reject(_value):
        raise ValueError('invalid_json_number')

    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=reject)


@dataclass(frozen=True)
class Principal:
    scope: str
    actor: str
    permissions: frozenset[str]

    def authorize(self, scope, actor, action):
        return scope == self.scope and actor == self.actor and action in self.permissions


class TokenIdentity:
    """Local reference adapter. Config stores digests, never bearer secrets."""
    def __init__(self, tokens):
        self._tokens = tokens

    @classmethod
    def load(cls, path):
        with path.open('rb') as stream:
            raw = stream.read(_MAX_CONFIG + 1)
        if len(raw) > _MAX_CONFIG:
            raise ValueError('invalid_identity_config')
        try:
            document = strict_json(raw)
            if (type(document) is not dict or set(document) != {'profile', 'principals'}
                    or document['profile'] != PROFILE or type(document['principals']) is not list
                    or not 1 <= len(document['principals']) <= 128):
                raise ValueError()
            tokens, identities = {}, set()
            for record in document['principals']:
                if type(record) is not dict or set(record) != {'scope', 'actor', 'token_sha256', 'permissions'}:
                    raise ValueError()
                scope, actor, digest = (record[key] for key in ('scope', 'actor', 'token_sha256'))
                permissions = record['permissions']
                if (not all(type(value) is str and _IDENTITY.fullmatch(value) for value in (scope, actor))
                        or type(digest) is not str or not _DIGEST.fullmatch(digest)
                        or type(permissions) is not list or not all(type(p) is str for p in permissions)):
                    raise ValueError()
                grants = frozenset(permissions)
                if (len(grants) != len(permissions) or not grants or not grants <= PERMISSIONS
                        or digest in tokens or (scope, actor) in identities):
                    raise ValueError()
                tokens[digest] = Principal(scope, actor, grants)
                identities.add((scope, actor))
        except (ValueError, RecursionError):
            raise ValueError('invalid_identity_config') from None
        return cls(tokens)

    def __call__(self, authorization):
        if not authorization.startswith('Bearer '):
            return None
        token = authorization[7:]
        if not _TOKEN.fullmatch(token):
            return None
        return self._tokens.get(sha256(token.encode('ascii')).hexdigest())
