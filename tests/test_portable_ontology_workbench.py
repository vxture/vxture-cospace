"""Portable host composition and permission boundaries without the CoSpace server."""
from contextlib import contextmanager
from copy import deepcopy

import pytest

from packages.ontology.kernel import Catalog, builtin_catalog
from packages.ontology.kernel.authoring import AuthoringError
from packages.ontology.kernel.workbench import DefinitionWorkbench


class MemoryPort:
    def __init__(self):
        self.states = {}
        self.opened = 0

    @contextmanager
    def transaction(self, scope):
        self.opened += 1
        state = deepcopy(self.states.get(scope, {}))
        yield state
        self.states[scope] = state


def test_host_can_independently_select_templates_and_author_capabilities():
    core = builtin_catalog().export('core')
    templates = Catalog(core['modules'])
    store = MemoryPort()
    roles = {
        'author': {'read', 'read_private', 'edit', 'submit'},
        'reviewer': {'read', 'read_private', 'review'},
        'publisher': {'read', 'publish'},
        'reader': {'read'},
    }

    def workspace(actor, scope='acme'):
        return DefinitionWorkbench(store, scope, actor, templates=templates,
            authorize=lambda s, a, action: s in {'acme', 'other'} and action in roles.get(a, set()))

    author, reviewer, publisher, reader = (workspace(a) for a in roles)
    assert [m['reference']['module_id'] for m in reader.released_library()['modules']] == ['core']
    with pytest.raises(AuthoringError, match='module_not_found'):
        reader.read('electrical')

    draft = author.change(dict(action='save', request_id='a' * 32, module_id='core',
                               expected_revision=0, bundle=core, base_reference=None))
    review = author.change(dict(action='submit', request_id='b' * 32, module_id='core', expected_revision=1))
    submit_id = review['review_id']
    opened = store.opened
    report = reviewer.read('core')
    assert store.opened == opened + 1
    assert report['draft']['sha256'] == report['validation']['draft_sha256'] == draft['sha256']
    assert report['comparison']['revision'] == draft['revision']
    assert report['reviews'][0]['can_decide'] and not author.read('core')['reviews'][0]['can_decide']
    assert reviewer.review_definition(submit_id)['modules'][0]['definition'] == core['modules'][0]
    assert workspace('reviewer', 'other').read('core')['draft'] is None

    summary = reader.read('core')
    assert not summary['can_manage'] and summary['draft'] is None and summary['reviews'] == []
    validate = dict(action='validate', module_id='core', revision=1)
    assert author.change(validate)['valid']
    opened = store.opened
    with pytest.raises(AuthoringError, match='forbidden'):
        reader.change(validate)
    with pytest.raises(AuthoringError, match='forbidden'):
        reader.review_definition(submit_id)
    assert store.opened == opened

    decision = dict(action='decide', request_id='c' * 32, review_id=submit_id,
                    decision='approved', reason='Synthetic host test')
    with pytest.raises(AuthoringError, match='forbidden'):
        author.change(decision)
    with pytest.raises(AuthoringError, match='invalid_request'):
        reader.change({**decision, 'actor': 'reviewer', 'scope': 'acme'})
    reviewer.change(decision)
    publish = dict(action='publish', request_id='d' * 32, review_id=submit_id, expected_revision=1)
    with pytest.raises(AuthoringError, match='forbidden'):
        reviewer.change(publish)
    frozen = publisher.change(publish)
    assert reader.definition(frozen['reference'])['modules'][0]['reference'] == frozen['reference']
    assert reader.released_library()['modules'][0]['published_at'] == frozen['published_at']
    assert workspace('reader', 'other').read('core')['releases'] == []


def test_public_workspace_reads_authorize_before_touching_the_port():
    store = MemoryPort()
    denied = DefinitionWorkbench(store, 'library', 'unknown', authorize=lambda *args: 1)
    reference = builtin_catalog().describe()['modules'][0]['reference']
    for read in (denied.released_library, lambda: denied.read('core'), lambda: denied.definition(reference)):
        with pytest.raises(AuthoringError, match='forbidden'):
            read()
    assert store.opened == 0
