from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest
from pydantic import ValidationError

from packages.service.scene_registrations import SceneRegistrations, RegistrationError


@pytest.fixture
def registration():
    return json.loads(Path('contracts/examples/spatial-registration-campus.json').read_text(encoding='utf-8'))


def service(root, actor='engineer', scope='workspace'):
    return SceneRegistrations(root, scope, actor, None, clock=lambda: '2026-11-21T00:00:00Z')


def source(document):
    return {'source_sha256': document['source']['manifest_sha256'], 'model_source': document['source']}


def command(document, action='save', revision=0, key=1, **changes):
    return {'space_id': document['source']['space_id'], 'candidate_id': document['source']['candidate_id'],
            'source_sha256': document['source']['manifest_sha256'], 'expected_revision': revision,
            'request_id': f'{key:032x}', 'action': action, 'reason': 'documented survey review',
            **({'document': document} if action == 'save' else {}), **changes}


def approval(document):
    return {'evidence_note': 'survey records and independent checks reviewed',
            'valid_from': '2026-11-20T00:00:00Z', 'valid_until': '2026-11-22T00:00:00Z',
            'bounds_m': document['source']['bounds_m'], 'control_evidence_verified': True,
            'independent_checks_verified': True, 'datum_verified': True, 'extent_verified': True}


def test_persistence_separate_review_adoption_and_fixed_old_revision(tmp_path, registration):
    registration['synthetic'] = False
    writer, reviewer = service(tmp_path), service(tmp_path, 'reviewer')
    bound = source(registration)
    assert writer.read(bound)['revision'] == 0
    assert not writer.path.exists()
    saved = writer.change(bound, command(registration))
    assert saved['revision'] == 1
    assert writer.change(bound, command(registration)) == saved
    writer.change(bound, command(registration, 'submit', 1, 2))
    approved = reviewer.change(bound, command(registration, 'approve', 2, 3,
                                               approval=approval(registration)), can_review=True)
    assert approved['review_status'] == 'approved' and approved['adopted_revision'] is None
    writer.change(bound, command(registration, 'adopt', 3, 4))
    before = writer.read(bound)
    assert before['adopted']['revision'] == 3
    assert before['adopted']['reviewed_by'] == 'reviewer'
    assert not before['can_focus_geographic_map'] and not before['included_in_publication']
    edited = deepcopy(registration)
    edited['controls'][0]['target_m'][2] += .01
    writer.change(bound, command(edited, revision=4, key=5))
    current = service(tmp_path).read(bound)
    assert current['review_status'] == 'draft'
    assert current['adopted'] == before['adopted']
    assert writer.fixed(bound, 1)['document'] == registration
    assert service(tmp_path, scope='other').read(bound)['document'] is None
    writer.change(bound, command(registration, 'clear_adoption', 5, 6))
    assert writer.read(bound)['adopted'] is None
    assert writer.fixed(bound, 3)['review_status'] == 'approved'


def test_synthetic_or_failed_controls_cannot_enter_approval(tmp_path, registration):
    writer = service(tmp_path)
    writer.change(source(registration), command(registration))
    with pytest.raises(RegistrationError, match='synthetic_not_approvable'):
        writer.change(source(registration), command(registration, 'submit', 1, 2))
    registration['synthetic'] = False
    registration['controls'][5]['target_m'][0] += .5
    writer.change(source(registration), command(registration, revision=1, key=3))
    with pytest.raises(RegistrationError, match='checks_failed'):
        writer.change(source(registration), command(registration, 'submit', 2, 4))


def test_review_independence_evidence_time_extent_and_permissions(tmp_path, registration):
    registration['synthetic'] = False
    bound = source(registration)
    writer, reviewer = service(tmp_path), service(tmp_path, 'reviewer')
    writer.change(bound, command(registration))
    writer.change(bound, command(registration, 'submit', 1, 2))
    approve = command(registration, 'approve', 2, 3, approval=approval(registration))
    with pytest.raises(RegistrationError, match='review_denied'):
        reviewer.change(bound, approve)
    with pytest.raises(RegistrationError, match='independent_reviewer'):
        writer.change(bound, approve, can_review=True)
    for value in (False, 1, 'true'):
        bad = deepcopy(approve)
        bad['approval']['independent_checks_verified'] = value
        with pytest.raises((RegistrationError, ValidationError)):
            reviewer.change(bound, bad, can_review=True)
    for field, value in [('valid_from', '2026-11-21'), ('valid_until', '2026-11-19T00:00:00Z')]:
        bad = deepcopy(approve)
        bad['approval'][field] = value
        with pytest.raises((RegistrationError, ValidationError)):
            reviewer.change(bound, bad, can_review=True)
    bad = deepcopy(approve)
    bad['approval']['bounds_m'][1][0] += 1
    with pytest.raises(RegistrationError, match='extent_outside_model'):
        reviewer.change(bound, bad, can_review=True)
    approve['approval']['valid_from'] = '2026-11-21T01:00:00Z'
    reviewer.change(bound, approve, can_review=True)
    with pytest.raises(RegistrationError, match='outside_valid_time'):
        writer.change(bound, command(registration, 'adopt', 3, 4))


def test_optimistic_lock_idempotency_source_binding_and_corruption(tmp_path, registration):
    writer, bound = service(tmp_path), source(registration)
    def save(key):
        try:
            return writer.change(bound, command(registration, key=key))
        except RegistrationError as exc:
            return str(exc)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, [1, 2]))
    assert sum(isinstance(value, dict) for value in results) == 1
    assert 'registration_revision_changed' in results
    winner = 1 if isinstance(results[0], dict) else 2
    bad = command(registration, key=winner, reason='changed payload')
    with pytest.raises(RegistrationError, match='request_conflict'):
        writer.change(bound, bad)
    bad = deepcopy(registration)
    bad['source']['axes'] = ['east', 'north', 'up']
    with pytest.raises(RegistrationError, match='source_changed'):
        writer.change(bound, command(bad, revision=1, key=3))
    with sqlite3.connect(writer.path) as db:
        raw = db.execute('SELECT payload FROM revisions').fetchone()[0]
        value = json.loads(raw)
        value['report']['calculation_status'] = 'forged'
        raw = json.dumps(value).encode()
        db.execute('UPDATE revisions SET payload=?,digest=?', (raw, sha256(raw).hexdigest()))
    with pytest.raises(RegistrationError, match='store_integrity'):
        writer.read(bound)
