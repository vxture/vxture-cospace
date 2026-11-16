from copy import deepcopy

import pytest

from experiments.scripts.scene_graph_sample import sample
from experiments.scripts.scene_sg1_samples import identity_samples
from packages.spatial.scene_changes import compare_snapshots
from packages.spatial.scene_states import resolve_opening_state
from packages.spatial.scene_matching import propose_identity_matches


def state(document, **kwargs):
    return resolve_opening_state(document, 'door-l1', as_of=kwargs.get('as_of', '2026-11-16T00:03:00Z'),
                                 known_at=kwargs.get('known_at', '2026-11-16T00:03:00Z'))


def event(document, *, identity, source='synthetic-source', value='open',
          observed='2026-11-16T00:02:00Z', received='2026-11-16T00:02:01Z', expires='2026-11-16T00:04:00Z'):
    row = dict(document['observations'][0], id=identity, source_id=source, value=value,
               observed_at=observed, received_at=received, valid_until=expires)
    document['observations'].append(row)


def test_known_expired_unavailable_and_unknown_are_distinct():
    document = sample()
    assert state(document)['value'] == 'closed'
    assert state(document, as_of='2026-11-16T00:05:00Z')['status'] == 'expired'
    assert state(document, known_at='2026-11-16T00:00:00Z')['status'] == 'unavailable'
    document['observations'][0]['value'] = 'unknown'
    assert state(document)['status'] == 'unknown'
    assert state(document)['value'] is None


def test_late_arrival_does_not_replace_newer_observation():
    document = sample()
    event(document, identity='newer')
    event(document, identity='late-old', value='closed', observed='2026-11-16T00:01:00Z',
          received='2026-11-16T00:02:30Z')
    result = state(document)
    assert result['value'] == 'open'
    assert result['observation_ids'] == ['newer']
    assert state(document, known_at='2026-11-16T00:02:00Z')['value'] == 'closed'


def test_expired_latest_does_not_revive_older_long_lived_state():
    document = sample()
    event(document, identity='expired-newer', expires='2026-11-16T00:02:30Z')
    assert state(document)['status'] == 'expired'
    assert state(document)['expired_observation_ids'] == ['expired-newer']


@pytest.mark.parametrize('same_source', [True, False])
def test_equal_time_or_cross_source_disagreement_is_conflict(same_source):
    document = sample()
    if not same_source:
        document['sources'].append(dict(id='source-b', kind='synthetic_fixture'))
    event(document, identity='alternative', source='synthetic-source' if same_source else 'source-b',
          observed='2026-11-16T00:00:00Z', received='2026-11-16T00:00:03Z')
    result = state(document)
    assert result['status'] == 'conflict'
    assert result['value'] is None
    assert len(result['observation_ids']) == 2
    before = deepcopy(document)
    document['observations'].reverse()
    reordered = state(document)
    original = state(before)
    assert reordered['status'] == original['status']
    assert reordered['observation_ids'] == original['observation_ids']
    assert reordered['source'] != original['source']  # Array order is part of the pinned source encoding.


def test_history_is_fixed_and_does_not_mutate_structure():
    document = sample()
    before = deepcopy(document)
    result = state(document)
    result['observation_ids'].clear()
    assert document == before
    assert len(document['connections']) == 3
    assert state(document)['real_release_ready'] is False
    assert state(document)['cursor'] != state(document, known_at='2026-11-16T00:02:00Z')['cursor']
    with pytest.raises(ValueError, match='subject_required'):
        resolve_opening_state(document, 'cabinet', as_of='2026-11-16T00:03:00Z', known_at='2026-11-16T00:03:00Z')
    with pytest.raises(ValueError, match='not_found'):
        resolve_opening_state(document, 'missing', as_of='2026-11-16T00:03:00Z', known_at='2026-11-16T00:03:00Z')


def test_changes_keep_description_and_physical_change_separate():
    base = sample()
    target = deepcopy(base)
    target['snapshot_id'] = 'next'
    door = next(row for row in target['entities'] if row['id'] == 'door-l1')
    door.update(name='new description', revision=2)
    target['observations'][0]['value'] = 'open'
    report = compare_snapshots(base, target)
    assert report['sections']['entities']['revised'] == ['door-l1']
    assert report['sections']['observations']['revised'] == ['door-state-01']
    assert report['sections']['connections']['revised'] == []
    assert report['affected_entity_ids'] == ['door-l1']
    assert report['real_release_ready'] is False
    door['revision'] = 1
    with pytest.raises(ValueError, match='requires_revision'):
        compare_snapshots(base, target)


def test_split_proposal_is_preserved_and_not_automatically_adopted():
    base, target, drafts = identity_samples()
    report = compare_snapshots(base, target, identity_changes=drafts['unresolved'])
    assert report['identity']['unresolved_event_ids'] == ['proposal-unresolved']
    assert report['identity']['identity_verified'] is False
    assert 'connection-door-l1' in report['sections']['connections']['removed']
    assert {'door-l1', 'room-l1', 'corridor-l1'} <= set(report['affected_entity_ids'])


def test_matching_proposes_both_split_spaces_without_adoption():
    base, target, _ = identity_samples()
    result = propose_identity_matches(base, target, maximum_distance_m=10)
    row = next(row for row in result['proposals'] if row['source_id'] == 'room-l1')
    assert {c['target_id'] for c in row['candidates']} == {'room-l1-a', 'room-l1-b'}
    assert all(c['approximate_box_iou'] == .5 for c in row['candidates'])
    assert row['status'] == 'unresolved'
    assert result['automatic_adoption'] is result['identity_verified'] is False
    limited = propose_identity_matches(base, target, maximum_distance_m=10, top_k=1)['proposals'][0]
    assert limited['truncated']
    assert limited['candidate_count_before_limit'] == 2
    assert not propose_identity_matches(base, target, maximum_distance_m=.1)['proposals'][0]['candidates']
    for value in (0, True, float('nan')):
        with pytest.raises(ValueError, match='configuration'):
            propose_identity_matches(base, target, maximum_distance_m=value)


def test_evidence_change_marks_referencing_entities_affected():
    base = sample()
    target = deepcopy(base)
    target['snapshot_id'] = 'new-evidence'
    target['evidence'][0]['description'] = 'revised synthetic evidence'
    result = compare_snapshots(base, target)
    assert result['sections']['evidence']['revised'] == ['fixture']
    assert set(result['affected_entity_ids']) == {row['id'] for row in base['entities']}


def test_consistent_sources_agree_without_priority_and_future_observations_are_excluded():
    document = sample()
    document['sources'].append(dict(id='source-b', kind='synthetic_fixture'))
    event(document, identity='agrees', source='source-b', value='closed')
    event(document, identity='future', observed='2026-11-16T00:04:00Z', received='2026-11-16T00:04:01Z',
          expires='2026-11-16T00:05:00Z')
    result = state(document)
    assert result['value'] == 'closed'
    assert result['observation_ids'] == ['agrees', 'door-state-01']
