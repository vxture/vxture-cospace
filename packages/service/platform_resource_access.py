"""Request-local authorization adapter: re-resolve saved ownership, then check policy.

No polling, export, inferred legacy ownership, cookies or browser-supplied identity.
The authorized-workbench HTTP gate calls this before admitting business routes.
"""
import json
import re
from packages.lifecycle.preview_scope import scope, match


class PlatformResourceAccess:
    def __init__(self, directory, jobs, policy):
        self.directory, self.jobs, self.policy = directory, jobs, policy

    def space(self, principal, space_id, capability):
        # Permission first: deny ungranted/nonexistent IDs without an existence oracle.
        self.policy.require(principal, space_id, capability)
        return scope(self.directory, space_id)

    def artifact(self, principal, artifact, capability, requested_space=None):
        if not isinstance(artifact, str) or ':' not in artifact:
            raise PermissionError('space_access_denied')
        kind, identity = artifact.split(':', 1)
        if kind == 'publication' and re.fullmatch(r'preview-[a-f0-9]{16}', identity):
            path = self.jobs.root / 'publications' / identity / 'publication.json'
        elif kind == 'candidate' and re.fullmatch(r'build-[A-Za-z0-9-]+', identity):
            path = self.jobs.root / identity / 'job.json'
        elif kind == 'input' and re.fullmatch(r'input-[a-f0-9]{16}', identity) and self.jobs.inputs:
            path = self.jobs.inputs.root / (identity + '.json')
        else:
            raise PermissionError('space_access_denied')
        try:
            record = json.loads(path.read_bytes())
            space_id = record['space_id']
            if not isinstance(space_id, str) or record['id'] != identity or requested_space is not None and requested_space != space_id:
                raise ValueError('ownership_mismatch')
            ownership = self.space(principal, space_id, capability)
            match(record, ownership)
            return ownership
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise PermissionError('space_access_denied') from exc
