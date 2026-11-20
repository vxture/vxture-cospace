"""CoSpace assembly of portable authoring, with trusted scope/actor from HTTP."""
from copy import deepcopy
from hashlib import sha256

from packages.ontology.authoring_sqlite import SQLiteAuthoringPort
from packages.ontology.kernel import Catalog, builtin_catalog, canonical_bytes
from packages.ontology.kernel.authoring import DefinitionAuthoring, AuthoringError


class DefinitionWorkbench:
    def __init__(self, root, scope, actor, can_manage):
        self.scope, self.actor, self.can_manage = scope, actor, can_manage
        self.service = DefinitionAuthoring(SQLiteAuthoringPort(root),
            authorize=lambda s, a, action: s == scope and a == actor and (action == 'read' or can_manage))

    def read(self, module_id):
        releases = self.service.list_releases(self.scope, self.actor, module_id)
        try:
            draft = self.service.read_draft(self.scope, self.actor, module_id) if self.can_manage else None
        except AuthoringError as exc:
            if exc.code != 'draft_not_found':
                raise
            draft = None
        if releases:
            source = self.service.read_release(self.scope, self.actor, releases[0]['reference'])['bundle']
        else:
            try:
                source = builtin_catalog().export(module_id)
            except ValueError:
                if draft is None:
                    raise AuthoringError('module_not_found') from None
                source = draft['bundle']
        reviews = []
        if self.can_manage:
            with self.service.port.transaction(self.scope) as state:
                matching = [r for r in state.get('reviews', {}).values() if r['module_id'] == module_id]
                for review in sorted(matching, key=lambda r: (r['submitted_at'], r['review_id']), reverse=True)[:50]:
                    item = {k: deepcopy(v) for k, v in review.items() if k != 'submitted_bundle'}
                    item['stale'] = draft is None or draft['revision'] != review['revision'] or draft['sha256'] != review['draft_sha256']
                    item['can_decide'] = not item['stale'] and review['state'] == 'pending' and review['submitted_by'] != self.actor
                    reviews.append(item)
        return {'profile': 'vxture.ontology-workbench/0.1', 'module_id': module_id,
                'can_manage': self.can_manage, 'draft': draft, 'source_bundle': source,
                'releases': releases, 'reviews': reviews,
                'validation': self.service.validate(self.scope, self.actor, module_id, draft['revision']) if draft else None,
                'comparison': self.service.compare(self.scope, self.actor, module_id, draft['revision']) if draft else None}

    def change(self, body):
        if not isinstance(body, dict) or 'action' not in body:
            raise AuthoringError('invalid_request')
        actions = {
            'save': ('save', {'module_id', 'expected_revision', 'bundle', 'base_reference'}),
            'validate': ('validate', {'module_id', 'revision'}),
            'submit': ('submit', {'module_id', 'expected_revision'}),
            'decide': ('decide', {'review_id', 'decision', 'reason'}),
            'publish': ('publish', {'review_id', 'expected_revision'}),
        }
        action = body['action']
        if not isinstance(action, str) or action not in actions:
            raise AuthoringError('invalid_request')
        method, fields = actions[action]
        request_fields = set() if action == 'validate' else {'request_id'}
        if set(body) != {'action'} | fields | request_fields:
            raise AuthoringError('invalid_request')
        args = {k: body[k] for k in fields | request_fields}
        return getattr(self.service, method)(self.scope, self.actor, **args)

    def released_library(self):
        """Directory summaries may mix versions; fixed reads use each frozen bundle."""
        result = builtin_catalog().describe()
        entries = {e['reference']['module_id']: e for e in result['modules']}
        with self.service.port.transaction(self.scope) as state:
            latest = {}
            for release in state.get('releases', {}).values():
                identity = release['reference']['module_id']
                order = tuple(map(int, release['reference']['version'].split('.')))
                if identity not in latest or order > latest[identity][0]:
                    latest[identity] = (order, release)
            for identity, (_, release) in latest.items():
                self.service._release(state, release['reference'])
                definition = next(m for m in release['bundle']['modules'] if m['module_id'] == identity)
                entries[identity] = {'reference': release['reference'], 'definition': definition,
                                     'published_at': release['published_at']}
        result['modules'] = [entries[k] for k in sorted(entries)]
        result['library_sha256'] = sha256(canonical_bytes(result['modules'])).hexdigest()
        return result

    def definition(self, reference):
        try:
            release = self.service.read_release(self.scope, self.actor, reference)
            return Catalog.from_bytes(canonical_bytes(release['bundle'])).describe()
        except AuthoringError as exc:
            if exc.code != 'release_not_found':
                raise
            # Exact pre-existing built-in references remain readable after overlay upgrades.
            for entry in builtin_catalog().describe()['modules']:
                if entry['reference'] == reference:
                    return Catalog.from_bytes(canonical_bytes(builtin_catalog().export(reference['module_id']))).describe()
            raise

    def review_definition(self, review_id):
        if not self.can_manage:
            raise AuthoringError('forbidden')
        review = self.service.read_review(self.scope, self.actor, review_id)
        return Catalog.from_bytes(canonical_bytes(review['submitted_bundle'])).describe()
