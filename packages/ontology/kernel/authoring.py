"""Portable authoring use cases. Storage and authorization are injected ports.

No database, HTTP, platform identity, scene state or network imports. Definition
validation is separate from draft persistence and artifact release governance.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import re

from .catalog import Catalog, CatalogError, ID, VERSION, MAX_BYTES, canonical_bytes
from typing import ContextManager, Protocol


class AuthoringPort(Protocol):
    """Trusted transactional storage port; implementation controls durability."""
    def transaction(self, scope: str) -> ContextManager[dict]: ...


class AuthoringError(ValueError):
    def __init__(self, code, path='/'):
        self.code, self.path = code, path
        super().__init__(f'{code}: {path}')


def _require(value, code, path='/'):
    if not value:
        raise AuthoringError(code, path)


def _text(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 500 and all(ord(c) >= 32 for c in value)


def _version(value):
    return tuple(int(part) for part in value.split('.'))


def _sha(value):
    return sha256(canonical_bytes(value)).hexdigest()


def _module(bundle, identity):
    return next(m for m in bundle['modules'] if m.get('module_id') == identity)


def _key(reference):
    return reference['module_id'] + '@' + reference['version']


def compare_definitions(before, after):
    """Deterministic structural diff, not a promise of instance compatibility."""
    result = []

    def walk(old, new, path):
        if type(old) is dict and type(new) is dict:
            for key in sorted(old.keys() | new.keys()):
                child = path + '/' + key.replace('~', '~0').replace('/', '~1')
                if key not in old:
                    result.append({'path': child, 'change': 'added'})
                elif key not in new:
                    result.append({'path': child, 'change': 'removed'})
                else:
                    walk(old[key], new[key], child)
        elif canonical_bytes(old) != canonical_bytes(new):
            result.append({'path': path or '/', 'change': 'changed'})

    walk(before, after, '')
    return result


class DefinitionAuthoring:
    """Port.transaction(scope) yields isolated mutable state and commits atomically.

    The port must serialize concurrent mutations, roll back on exceptions and
    retain state between calls. authorize(scope, actor, action) must return True.
    Authentication and permission mapping always belong to the host adapter.
    """

    def __init__(self, port, *, authorize, clock=None):
        self.port, self.authorize = port, authorize
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))

    def _access(self, scope, actor, action):
        _require(_text(scope) and _text(actor), 'invalid_context')
        _require(self.authorize(scope, actor, action) is True, 'forbidden')

    def _mutate(self, scope, actor, action, request_id, payload, operation):
        self._access(scope, actor, action)
        _require(type(request_id) is str and re.fullmatch('[a-f0-9]{32}', request_id), 'invalid_request_id')
        digest = _sha({'actor': actor, 'action': action, 'payload': payload})
        with self.port.transaction(scope) as state:
            for collection in ('drafts', 'reviews', 'releases', 'receipts'):
                state.setdefault(collection, {})
            previous = state['receipts'].get(request_id)
            if previous:
                _require(previous['sha256'] == digest, 'request_conflict')
                return deepcopy(previous['result'])
            result = operation(state)
            state['receipts'][request_id] = {'sha256': digest, 'result': deepcopy(result)}
            return deepcopy(result)

    @staticmethod
    def _draft(state, identity, revision=None):
        _require(type(identity) is str and ID.fullmatch(identity), 'invalid_module_id')
        draft = state.get('drafts', {}).get(identity)
        _require(draft is not None, 'draft_not_found')
        _require(draft['sha256'] == _sha(draft['bundle']), 'draft_integrity')
        if revision is not None:
            _require(type(revision) is int and revision == draft['revision'], 'revision_changed')
        return draft

    @staticmethod
    def _validation(draft):
        try:
            catalog = Catalog.from_bytes(canonical_bytes(draft['bundle']))
            # Only target + closure may be frozen; unrelated modules cannot be released accidentally.
            closed = catalog.export(draft['module_id'])
            _require(closed == catalog.export(), 'unrelated_modules')
        except (CatalogError, AuthoringError) as exc:
            return {'valid': False, 'revision': draft['revision'], 'draft_sha256': draft['sha256'],
                    'diagnostics': [{'code': exc.code, 'path': exc.path}]}
        return {'valid': True, 'revision': draft['revision'], 'draft_sha256': draft['sha256'], 'diagnostics': []}

    def save(self, scope, actor, request_id, *, module_id, expected_revision, bundle, base_reference=None):
        """Save a draft, including semantically invalid intermediate edits.

        Draft identity/version and transport shape must still be well formed.
        Dependencies are explicit bytes in the bundle, never resolved from latest.
        """
        self._access(scope, actor, 'edit')
        _require(type(module_id) is str and ID.fullmatch(module_id), 'invalid_module_id')
        _require(type(expected_revision) is int and expected_revision >= 0, 'invalid_revision')
        try:
            raw = canonical_bytes(bundle)
        except (ValueError, TypeError, RecursionError, OverflowError):
            raise AuthoringError('invalid_bundle') from None
        _require(len(raw) <= MAX_BYTES, 'size_budget')
        _require(type(bundle) is dict and set(bundle) == {'profile', 'modules'} and
                 bundle['profile'] == 'vxture.ontology-library/0.1' and type(bundle['modules']) is list
                 and 1 <= len(bundle['modules']) <= 32, 'invalid_bundle')
        _require(all(type(m) is dict and type(m.get('module_id')) is str for m in bundle['modules']), 'invalid_bundle')
        _require(len({m['module_id'] for m in bundle['modules']}) == len(bundle['modules']), 'duplicate_module')
        _require(sum(m['module_id'] == module_id for m in bundle['modules']) == 1, 'invalid_module_id')
        target = _module(bundle, module_id)
        _require(type(target.get('version')) is str and VERSION.fullmatch(target['version']) and
                 target.get('status') == 'draft', 'invalid_draft')
        payload = {'module_id': module_id, 'expected_revision': expected_revision,
                   'bundle': bundle, 'base_reference': base_reference}

        def operation(state):
            previous = state['drafts'].get(module_id)
            _require((previous['revision'] if previous else 0) == expected_revision, 'revision_changed')
            if previous:
                self._draft(state, module_id, expected_revision)
                if base_reference != previous['base_reference']:
                    base = self._release(state, base_reference)
                    _require(base['bundle_sha256'] == previous['sha256'], 'base_reference_changed')
            if base_reference is not None:
                self._release(state, base_reference)
                _require(base_reference['module_id'] == module_id, 'base_reference_mismatch')
                _require(_version(target['version']) > _version(base_reference['version']), 'version_not_advanced')
            draft = {'module_id': module_id, 'revision': expected_revision + 1,
                     'bundle': deepcopy(bundle), 'sha256': _sha(bundle), 'base_reference': deepcopy(base_reference),
                     'updated_at': self.clock(), 'updated_by': actor}
            state['drafts'][module_id] = draft
            return draft

        return self._mutate(scope, actor, 'edit', request_id, payload, operation)

    def read_draft(self, scope, actor, module_id):
        self._access(scope, actor, 'read')
        with self.port.transaction(scope) as state:
            return deepcopy(self._draft(state, module_id))

    def validate(self, scope, actor, module_id, revision):
        self._access(scope, actor, 'read')
        _require(type(revision) is int and revision >= 1, 'invalid_revision')
        with self.port.transaction(scope) as state:
            return self._validation(self._draft(state, module_id, revision))

    @staticmethod
    def _release(state, reference):
        _require(type(reference) is dict and set(reference) == {'module_id', 'version', 'sha256'} and
                 all(type(v) is str for v in reference.values()), 'invalid_reference')
        release = state.get('releases', {}).get(_key(reference))
        _require(release is not None and release['reference'] == reference, 'release_not_found')
        # Read integrity is checked, not merely trusted because the row exists.
        module = _module(release['bundle'], reference['module_id'])
        _require(_sha(module) == reference['sha256'], 'release_integrity')
        _require(_sha(release['bundle']) == release['bundle_sha256'], 'release_integrity')
        Catalog.from_bytes(canonical_bytes(release['bundle']))
        return release

    @staticmethod
    def _publishable(state, draft):
        report = DefinitionAuthoring._validation(draft)
        _require(report['valid'], 'validation_failed')
        target = _module(draft['bundle'], draft['module_id'])
        _require(_key(target) not in state['releases'], 'version_exists')
        versions = [_version(r['reference']['version']) for r in state['releases'].values()
                    if r['reference']['module_id'] == draft['module_id']]
        _require(not versions or _version(target['version']) > max(versions), 'version_not_advanced')
        # Every dependency must have an immutable release, not just another mutable draft.
        for module in draft['bundle']['modules']:
            if module['module_id'] != draft['module_id']:
                reference = {key: module[key] for key in ('module_id', 'version')}
                reference['sha256'] = _sha(module)
                DefinitionAuthoring._release(state, reference)
        return target

    def submit(self, scope, actor, request_id, *, module_id, expected_revision):
        self._access(scope, actor, 'submit')
        _require(type(expected_revision) is int and expected_revision >= 1, 'invalid_revision')
        def operation(state):
            draft = self._draft(state, module_id, expected_revision)
            self._publishable(state, draft)
            review = {'review_id': request_id, 'module_id': module_id, 'revision': draft['revision'],
                      'draft_sha256': draft['sha256'], 'submitted_by': actor, 'submitted_at': self.clock(),
                      'submitted_bundle': deepcopy(draft['bundle']),
                      'state': 'pending', 'decision_by': None, 'decision_at': None, 'reason': None}
            state['reviews'][request_id] = review
            return review
        return self._mutate(scope, actor, 'submit', request_id,
                            {'module_id': module_id, 'expected_revision': expected_revision}, operation)

    def decide(self, scope, actor, request_id, *, review_id, decision, reason):
        self._access(scope, actor, 'review')
        _require(type(review_id) is str and re.fullmatch('[a-f0-9]{32}', review_id), 'invalid_review_id')
        _require(decision in ('approved', 'rejected') and _text(reason), 'invalid_decision')

        def operation(state):
            review = state['reviews'].get(review_id)
            _require(review is not None, 'review_not_found')
            _require(review['state'] == 'pending', 'review_already_decided')
            _require(_sha(review['submitted_bundle']) == review['draft_sha256'], 'review_integrity')
            _require(review['submitted_by'] != actor, 'self_approval_forbidden')
            draft = self._draft(state, review['module_id'], review['revision'])
            _require(draft['sha256'] == review['draft_sha256'], 'review_stale')
            review.update(state=decision, decision_by=actor, decision_at=self.clock(), reason=reason)
            return review
        return self._mutate(scope, actor, 'review', request_id,
                            {'review_id': review_id, 'decision': decision, 'reason': reason}, operation)

    def publish(self, scope, actor, request_id, *, review_id, expected_revision):
        self._access(scope, actor, 'publish')
        _require(type(expected_revision) is int and expected_revision >= 1, 'invalid_revision')
        _require(type(review_id) is str and re.fullmatch('[a-f0-9]{32}', review_id), 'invalid_review_id')
        def operation(state):
            review = state['reviews'].get(review_id)
            _require(review is not None and review['state'] == 'approved', 'approval_required')
            _require(_sha(review['submitted_bundle']) == review['draft_sha256'], 'review_integrity')
            draft = self._draft(state, review['module_id'], expected_revision)
            _require(draft['revision'] == review['revision'] and draft['sha256'] == review['draft_sha256'], 'review_stale')
            target = self._publishable(state, draft)
            reference = {'module_id': target['module_id'], 'version': target['version'], 'sha256': _sha(target)}
            release = {'profile': 'vxture.ontology-release/0.1', 'state': 'published',
                       'reference': reference, 'bundle': deepcopy(draft['bundle']), 'bundle_sha256': draft['sha256'],
                       'published_at': self.clock(), 'published_by': actor, 'review': deepcopy(review)}
            state['releases'][_key(reference)] = release
            return release
        return self._mutate(scope, actor, 'publish', request_id,
                            {'review_id': review_id, 'expected_revision': expected_revision}, operation)

    def read_release(self, scope, actor, reference):
        self._access(scope, actor, 'read')
        with self.port.transaction(scope) as state:
            return deepcopy(self._release(state, reference))

    def read_review(self, scope, actor, review_id):
        self._access(scope, actor, 'read')
        _require(type(review_id) is str and re.fullmatch('[a-f0-9]{32}', review_id), 'invalid_review_id')
        with self.port.transaction(scope) as state:
            review = state.get('reviews', {}).get(review_id)
            _require(review is not None, 'review_not_found')
            _require(_sha(review['submitted_bundle']) == review['draft_sha256'], 'review_integrity')
            return deepcopy(review)

    def list_releases(self, scope, actor, module_id):
        self._access(scope, actor, 'read')
        _require(type(module_id) is str and ID.fullmatch(module_id), 'invalid_module_id')
        with self.port.transaction(scope) as state:
            return [{'reference': deepcopy(r['reference']), 'published_at': r['published_at']}
                    for r in sorted(state.get('releases', {}).values(),
                                    key=lambda r: _version(r['reference']['version']), reverse=True)
                    if r['reference']['module_id'] == module_id]

    def compare(self, scope, actor, module_id, revision):
        self._access(scope, actor, 'read')
        _require(type(revision) is int and revision >= 1, 'invalid_revision')
        with self.port.transaction(scope) as state:
            draft = self._draft(state, module_id, revision)
            base = self._release(state, draft['base_reference']) if draft['base_reference'] else None
            return {'revision': revision, 'base_reference': deepcopy(draft['base_reference']),
                    'changes': compare_definitions(_module(base['bundle'], module_id) if base else {},
                                                   _module(draft['bundle'], module_id))}
