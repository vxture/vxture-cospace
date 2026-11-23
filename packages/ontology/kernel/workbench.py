"""Transport-neutral authoring workspace for authenticated host adapters."""
from copy import deepcopy
from functools import cached_property
from hashlib import sha256

from .authoring import AuthoringError, DefinitionAuthoring, _module, _require, _version
from .catalog import Catalog, CatalogError, ID, builtin_catalog, canonical_bytes
from .exchange import export_closure


class DefinitionWorkbench:
    """Bind one trusted scope and actor to portable workspace operations.

    The host authenticates the principal and supplies an authorization policy.
    In addition to the authoring actions, the workspace checks read_private
    before exposing drafts or reviews. No transport data can set the context.
    """

    def __init__(self, port, scope, actor, *, authorize, templates=None, clock=None):
        self.service = DefinitionAuthoring(port, authorize=authorize, clock=clock)
        self._scope = scope
        self._actor = actor
        self._provided_templates = templates

    @cached_property
    def _templates(self):
        return builtin_catalog() if self._provided_templates is None else self._provided_templates

    def read(self, module_id):
        service, scope, actor = self.service, self._scope, self._actor
        service._access(scope, actor, 'read')
        _require(type(module_id) is str and ID.fullmatch(module_id), 'invalid_module_id')
        can_manage = service.authorize(scope, actor, 'read_private') is True
        can_review = can_manage and service.authorize(scope, actor, 'review') is True
        with service.port.transaction(scope) as state:
            releases = service._list_releases(state, module_id)
            draft = None
            if can_manage and module_id in state.get('drafts', {}):
                draft = deepcopy(service._draft(state, module_id))
            if releases:
                source = deepcopy(service._release(state, releases[0]['reference'])['bundle'])
            else:
                try:
                    source = self._templates.export(module_id)
                except CatalogError as exc:
                    if exc.code != 'module_not_found' or draft is None:
                        raise AuthoringError(exc.code, exc.path) from None
                    source = deepcopy(draft['bundle'])
            reviews = []
            if can_manage:
                matching = (r for r in state.get('reviews', {}).values() if r['module_id'] == module_id)
                for review in sorted(matching, key=lambda r: (r['submitted_at'], r['review_id']), reverse=True)[:50]:
                    item = {k: deepcopy(v) for k, v in review.items() if k != 'submitted_bundle'}
                    item['stale'] = (draft is None or draft['revision'] != review['revision']
                                     or draft['sha256'] != review['draft_sha256'])
                    item['can_decide'] = (can_review and not item['stale'] and review['state'] == 'pending'
                                          and review['submitted_by'] != actor)
                    reviews.append(item)
            return {'profile': 'vxture.ontology-workbench/0.1', 'module_id': module_id,
                    'can_manage': can_manage, 'draft': draft, 'source_bundle': source,
                    'releases': releases, 'reviews': reviews,
                    'validation': service._validation(draft) if draft else None,
                    'comparison': service._comparison(state, draft) if draft else None}

    def change(self, body):
        _require(isinstance(body, dict), 'invalid_request')
        action = body.get('action')
        actions = {
            'save': ('save', {'module_id', 'expected_revision', 'bundle', 'base_reference'}),
            'validate': ('validate', {'module_id', 'revision'}),
            'submit': ('submit', {'module_id', 'expected_revision'}),
            'decide': ('decide', {'review_id', 'decision', 'reason'}),
            'publish': ('publish', {'review_id', 'expected_revision'}),
        }
        _require(isinstance(action, str) and action in actions, 'invalid_request')
        method, fields = actions[action]
        fields = fields | (set() if action == 'validate' else {'request_id'})
        _require(set(body) == {'action'} | fields, 'invalid_request')
        if action == 'validate':
            self.service._access(self._scope, self._actor, 'read_private')
        return getattr(self.service, method)(self._scope, self._actor, **{key: body[key] for key in fields})

    def released_library(self):
        """A directory overlay; each published item's dependencies are read separately."""
        service, scope = self.service, self._scope
        service._access(scope, self._actor, 'read')
        result = self._templates.describe()
        entries = {e['reference']['module_id']: e for e in result['modules']}
        with service.port.transaction(scope) as state:
            latest = {}
            for release in state.get('releases', {}).values():
                ref = release['reference']
                identity, order = ref['module_id'], _version(ref['version'])
                if identity not in latest or order > latest[identity][0]:
                    latest[identity] = (order, ref)
            for identity, (_, reference) in latest.items():
                release = service._release(state, reference)
                entries[identity] = {'reference': deepcopy(reference),
                                     'definition': deepcopy(_module(release['bundle'], identity)),
                                     'published_at': release['published_at']}
        result['modules'] = [entries[key] for key in sorted(entries)]
        result['library_sha256'] = sha256(canonical_bytes(result['modules'])).hexdigest()
        return result

    def definition(self, reference):
        try:
            release = self.service.read_release(self._scope, self._actor, reference)
        except AuthoringError as exc:
            if exc.code != 'release_not_found':
                raise
            for entry in self._templates.describe()['modules']:
                if entry['reference'] == reference:
                    return Catalog(self._templates.export(reference['module_id'])['modules']).describe()
            raise
        return Catalog(release['bundle']['modules']).describe()

    def review_definition(self, review_id):
        self.service._access(self._scope, self._actor, 'read_private')
        review = self.service.read_review(self._scope, self._actor, review_id)
        return Catalog.from_bytes(canonical_bytes(review['submitted_bundle'])).describe()

    def export_release(self, reference):
        """Export the exact published closure, without candidate fallback or review metadata."""
        release = self.service.read_release(self._scope, self._actor, reference)
        return export_closure(release['bundle'], release['reference'])

    def preflight_import(self, raw):
        return self.service.preflight_import(self._scope, self._actor, raw)

    def import_draft(self, raw, *, request_id, expected_revision):
        return self.service.import_draft(self._scope, self._actor, raw,
                                         request_id=request_id, expected_revision=expected_revision)
