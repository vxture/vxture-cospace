from types import SimpleNamespace

import pytest

from packages.infrastructure.spatial_observation_store import ObservationJournal, ObservationStorageUnavailable
from packages.service.ifc_review_observations import read_review_observations
from packages.service.ifc_opening_observations import observation_scope
from packages.spatial.scene_identity import content_digest
from test_ifc_review_snapshot import review_env, structure_source, build, sha, filled
from test_ifc_type_proposals import ontology, mapping
from test_observation_journal import report

WHEN = '2026-11-17T00:05:00Z'


@pytest.fixture
def bound(review_env, tmp_path):
    principal = SimpleNamespace(issuer='https://example.invalid', org_id='test-org', workspace_id='test-workspace')
    snapshot = build(review_env)
    import json
    source = json.loads(snapshot['snapshot'])['source']
    store = ObservationJournal(tmp_path / 'journal', clock=lambda: '2026-11-17T00:01:00Z')
    scope = observation_scope(principal, source['space_id'], source['catalog_sha256'])
    store.register({'profile': 'cospace.opening-observation-registration/0.1', 'scope': scope,
                    'data_kind': 'ifc_design_candidate', 'subjects': [{'entity_id': 'door', 'role': 'door'}],
                    'producers': ['sensor-a']})
    return store, principal, snapshot, source, scope


def read(env, *, query=None, snapshot=None, ontology_raw=None, principal=None):
    store, actor, result, source, _ = env
    result = snapshot or result
    request = {'snapshot_sha256': sha(result['snapshot']), 'element_ids': ['e00002']} | (query or {})
    return read_review_observations(store, principal or actor, result['snapshot'], query=request,
        design_package=result['design_package'], expected_source=source, now=WHEN, ontology_raw=ontology_raw)


def replay(value):
    return {'replay': {key: str(value[key]) for key in ('as_of', 'known_at', 'through_sequence')},
            'expected_context_cursor': value['context_cursor']}


def test_context_binds_snapshot_and_fixed_journal_prefix_without_writing(bound):
    store, _, snapshot, _, scope = bound
    store.append(scope, report(entity_id='door'), authenticated_producer='sensor-a')
    before = store.path.read_bytes()
    result = read(bound)
    assert result['states'][0]['value'] == 'closed'
    assert result['context_cursor'] == content_digest({k: v for k, v in result.items() if k != 'context_cursor'})
    assert read(bound, query=replay(result)) == result
    assert store.path.read_bytes() == before
    assert sha(snapshot['snapshot']) == result['snapshot_sha256']
    assert 'test-org' not in str(result)
    assert 'sensor-a' not in str(result)
    assert 'evidence_sha256' not in str(result)
    for key in ('alignment_verified', 'ontology_bound', 'evidence_content_verified', 'clock_quality_verified', 'real_release_ready'):
        assert result[key] is False
    store.append(scope, report('corrected', entity_id='door', value='open', supersedes='event-1'),
                 authenticated_producer='sensor-a')
    assert read(bound)['states'][0]['value'] == 'open'
    assert read(bound, query=replay(result)) == result


def test_registered_no_reports_is_explicit_unavailable(bound):
    value = read(bound)
    assert value['states'][0]['status'] == 'unavailable'
    assert value['through_sequence'] == 0


@pytest.mark.parametrize('query,error', [
    ({'element_ids': ['e00002', 'e00002']}, 'duplicate_element'),
    ({'element_ids': ['e00001']}, 'door_required'),
    ({'element_ids': ['e99999']}, 'door_required'),
    ({'expected_context_cursor': 'a' * 64}, 'replay_required'),
    ({'replay': {'as_of': WHEN, 'known_at': WHEN, 'through_sequence': '0'}, 'expected_context_cursor': 'a' * 64}, 'context_changed'),
    ({'replay': {'as_of': '2026-11-18T00:00:00Z', 'known_at': WHEN, 'through_sequence': '0'}}, 'future'),
])
def test_invalid_context_is_rejected(bound, query, error):
    with pytest.raises(ValueError, match=error):
        read(bound, query=query)


def test_other_tenant_cannot_reuse_context_or_implicitly_register(bound):
    result = read(bound)
    other = SimpleNamespace(issuer='https://example.invalid', org_id='other-org', workspace_id='test-workspace')
    request = replay(result)
    with pytest.raises(ValueError, match='scope_not_registered'):
        read(bound, query=request, principal=other)


def test_identical_reports_in_other_registered_scope_do_not_match_context(bound):
    store, _, _, source, _ = bound
    result = read(bound)
    other = SimpleNamespace(issuer='https://example.invalid', org_id='other-org', workspace_id='test-workspace')
    scope = observation_scope(other, source['space_id'], source['catalog_sha256'])
    store.register({'profile': 'cospace.opening-observation-registration/0.1', 'scope': scope,
                    'data_kind': 'ifc_design_candidate', 'subjects': [{'entity_id': 'door', 'role': 'door'}],
                    'producers': ['sensor-a']})
    other_result = read(bound, principal=other)
    assert other_result['context_cursor'] != result['context_cursor']
    request = replay(result)
    with pytest.raises(ValueError, match='context_changed'):
        read(bound, query=request, principal=other)


def test_semantic_revision_changes_context_but_not_observation_cursor(bound, review_env):
    base = read(bound)
    vocabulary = ontology()
    revised = build(review_env, mapping=mapping(vocabulary), ontology_raw=vocabulary)
    current = read(bound, snapshot=revised, ontology_raw=vocabulary)
    assert current['observation_cursor'] == base['observation_cursor']
    assert current['context_cursor'] != base['context_cursor']
    assert current['states'] == base['states']
    request = replay(base)
    with pytest.raises(ValueError, match='context_changed'):
        read(bound, query=request, snapshot=revised, ontology_raw=vocabulary)


def test_annotation_revision_changes_context_without_touching_reports(bound, review_env):
    base = read(bound)
    revised = build(review_env, worksheet=filled(review_env[2]))
    value = read(bound, snapshot=revised)
    assert value['observation_cursor'] == base['observation_cursor']
    assert value['context_cursor'] != base['context_cursor']


def test_journal_corruption_is_not_an_empty_context(bound):
    from contextlib import closing
    import sqlite3
    store, _, _, _, scope = bound
    store.append(scope, report(entity_id='door'), authenticated_producer='sensor-a')
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute('UPDATE reports SET event_id=?', ('broken',))
    with pytest.raises(ObservationStorageUnavailable):
        read(bound)


def test_append_during_resolution_is_excluded_from_fixed_context(bound, monkeypatch):
    import packages.infrastructure.spatial_observation_store as module
    store, _, _, _, scope = bound
    store.append(scope, report(entity_id='door'), authenticated_producer='sensor-a')
    before = read(bound)
    original = module._resolved_state
    calls = []

    def append_during_read(*args):
        if not calls:
            calls.append(True)
            store.append(scope, report('new', entity_id='door', value='open', supersedes='event-1'),
                         authenticated_producer='sensor-a')
        return original(*args)

    monkeypatch.setattr(module, '_resolved_state', append_during_read)
    assert read(bound) == before
    assert read(bound)['states'][0]['value'] == 'open'
    assert read(bound, query=replay(before)) == before


def test_unregistered_object_and_wrong_data_kind_fail_closed(bound):
    from contextlib import closing
    import sqlite3
    from packages.spatial.scene_identity import canonical
    import json
    store, *_ = bound
    with closing(sqlite3.connect(store.path)) as db, db:
        key, raw = db.execute('SELECT scope,document FROM registrations').fetchone()
        registration = json.loads(raw)
        registration['subjects'][0]['entity_id'] = 'other-door'
        db.execute('UPDATE registrations SET document=? WHERE scope=?', (canonical(registration), key))
    with pytest.raises(ValueError, match='subject_not_registered'):
        read(bound)
    with closing(sqlite3.connect(store.path)) as db, db:
        registration['subjects'][0]['entity_id'] = 'door'
        registration['data_kind'] = 'synthetic'
        db.execute('UPDATE registrations SET document=? WHERE scope=?', (canonical(registration), key))
    with pytest.raises(ValueError, match='source_kind_mismatch'):
        read(bound)


def test_cli_read_is_replayable_and_never_overwrites(bound, tmp_path, monkeypatch):
    from experiments.scripts.ifc_review_observations import main
    from packages.spatial.scene_identity import canonical
    import json
    store, principal, result, source, _ = bound
    for name, raw in [('snapshot.json', result['snapshot']), ('design.bin', result['design_package']),
                      ('source.json', canonical(source)),
                      ('query.json', canonical({'snapshot_sha256': sha(result['snapshot']), 'element_ids': ['e00002']}))]:
        (tmp_path / name).write_bytes(raw)
    output = tmp_path / 'context.json'
    args = ['ifc_review_observations', '--snapshot', str(tmp_path / 'snapshot.json'),
        '--design-package', str(tmp_path / 'design.bin'), '--source', str(tmp_path / 'source.json'),
        '--query', str(tmp_path / 'query.json'), '--journal-root', str(store.path.parent),
        '--issuer', principal.issuer, '--organization', principal.org_id, '--workspace', principal.workspace_id,
        '--now', WHEN, '--output', str(output)]
    monkeypatch.setattr('sys.argv', args)
    before = store.path.read_bytes()
    main()
    value = json.loads(output.read_bytes())
    assert value == read(bound)
    assert store.path.read_bytes() == before
    with pytest.raises(FileExistsError):
        main()
    (tmp_path / 'query.json').write_bytes(canonical({'snapshot_sha256': sha(result['snapshot']),
        'element_ids': ['e00002']} | replay(value)))
    second = tmp_path / 'replay.json'
    monkeypatch.setattr('sys.argv', args[:-1] + [str(second)])
    main()
    assert json.loads(second.read_bytes()) == value


def test_schema_matches_strict_query_and_batch_budget(bound):
    import json
    from pathlib import Path
    from packages.service.ifc_review_observations import ReviewObservationQuery
    schema = json.loads(Path('contracts/schemas/ifc-review-observation-query-v0.1.schema.json').read_bytes())
    assert schema == ReviewObservationQuery.model_json_schema()
    for elements in ([], ['e00002'] * 129):
        with pytest.raises(ValueError):
            read(bound, query={'element_ids': elements})
