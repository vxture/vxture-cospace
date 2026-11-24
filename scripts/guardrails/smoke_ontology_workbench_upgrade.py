"""Verify actual B09c and B09d wheels against the same local state and a snapshot."""
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlencode

from smoke_ontology_host import DEFINITIONS, EXCHANGE, GROUPS, MODULE, run, start


def verify(old, current, ui, root):
    data, saved, recovered, config = [root / name for name in ('state', 'backup', 'restored', 'identity.json')]
    scope = 'synthetic-park'
    permissions = {
        'author': ['read', 'read_private', 'edit', 'submit'], 'reviewer': ['read', 'read_private', 'review'],
        'publisher': ['read', 'read_private', 'publish'], 'configuration': ['configure_groups'],
    }
    tokens = {actor: secrets.token_urlsafe(32) for actor in permissions}
    config.write_text(json.dumps({'profile': 'vxture.ontology-local-host/0.1', 'principals': [
        {'actor': actor, 'scope': scope, 'permissions': grants,
         'token_sha256': sha256(tokens[actor].encode()).hexdigest()} for actor, grants in permissions.items()]}),
        encoding='utf-8')

    def change(call, actor, action, marker, **fields):
        return call(DEFINITIONS, tokens[actor], {'action': action, 'request_id': f'{marker:032x}', **fields})

    def publish(call, review, revision, marker):
        change(call, 'reviewer', 'decide', marker, review_id=review['review_id'], decision='approved', reason='Fixture')
        return change(call, 'publisher', 'publish', marker + 1, review_id=review['review_id'], expected_revision=revision)

    def draft(call, identity, revision, marker, *, bundle=None, base=None):
        if bundle is None:
            bundle = call(DEFINITIONS + f'?module_id={identity}', tokens['author'])['source_bundle']
        change(call, 'author', 'save', marker, module_id=identity, expected_revision=revision,
               bundle=bundle, base_reference=base)
        return change(call, 'author', 'submit', marker + 1, module_id=identity, expected_revision=revision + 1)

    with start(old, data, config, root) as call:
        core = publish(call, draft(call, 'core', 0, 1), 1, 3)
        electrical = publish(call, draft(call, 'electrical', 0, 5), 1, 7)
        path = EXCHANGE + '?' + urlencode(electrical['reference'])
        before = call(path, tokens['author'])
        newer = call(DEFINITIONS + '?module_id=core', tokens['author'])['source_bundle']
        newer['modules'][0]['version'] = '0.2.0'
        pending = draft(call, 'core', 1, 9, bundle=newer, base=core['reference'])
        groups = call(GROUPS, tokens['configuration'])
        groups = call(GROUPS, tokens['configuration'], dict(request_id='a'*32, expected_revision=groups['revision'],
                      group_id=None, name='Synthetic zone', description='', sort_order=0, status='active', reason='Fixture'))
    run(old, root, 'backup', '--data-dir', data, '--output-dir', saved)

    with start(current, data, config, root, '--ui-dir', ui) as call:
        assert call(path, tokens['author']) == before
        assert call(GROUPS, tokens['configuration']) == groups
        assert call('/api/ontology-session', tokens['author'])['actor'] == 'author'
        assert call('/api/ontology-drafts', tokens['author'])['drafts'][0]['revision'] == 2
        assert call(DEFINITIONS + '?module_id=core', tokens['reviewer'])['reviews'][0]['can_decide']
        new = publish(call, pending, 2, 11)
        assert call(path, tokens['author']) == before

    # Code rollback reads the upgraded store; state rollback restores the earlier snapshot separately.
    with start(old, data, config, root) as call:
        assert call(path, tokens['author']) == before
        assert call(EXCHANGE + '?' + urlencode(new['reference']), tokens['author'])['reference'] == new['reference']
        assert call(GROUPS, tokens['configuration']) == groups
    run(old, root, 'restore', '--backup-dir', saved, '--data-dir', recovered)
    with start(old, recovered, config, root) as call:
        assert call(path, tokens['author']) == before
        assert call(DEFINITIONS + '?module_id=core', tokens['reviewer'])['reviews'][0]['state'] == 'pending'
        assert call(EXCHANGE + '?' + urlencode(new['reference']), tokens['author'], status=404)
    print('B09c -> B09d -> B09c: exact historical closure, pending approval, groups, upgraded store and snapshot passed.')


if __name__ == '__main__':
    old_wheel, new_wheel, ui = [Path(value).resolve(strict=True) for value in sys.argv[1:]]
    base = [sys.executable, '-I', '-S', '-c', MODULE]
    with TemporaryDirectory(prefix='ontology-upgrade-') as directory:
        verify([*base, str(old_wheel)], [*base, str(new_wheel)], ui, Path(directory))
