"""Fixed synthetic snapshot differences, not physical change or automatic identity adoption."""
from packages.spatial.scene_identity import snapshot_ref, validate_identity_changes


def _difference(before, after):
    a, b = {row['id']: row for row in before}, {row['id']: row for row in after}
    return dict(added=sorted(b.keys() - a.keys()), removed=sorted(a.keys() - b.keys()),
                revised=sorted(key for key in a.keys() & b.keys() if a[key] != b[key]))


def _subjects(key, row):
    if key == 'entities':
        return {row['id']}
    if key in ('geometry', 'observations'):
        return {row['entity_id']}
    if key == 'relations':
        return {row['source_id'], row['target_id']}
    return {row['connector_id'], *(port['space_id'] for port in row['ports'])}


def _changed_ids(difference):
    return set(difference['added'] + difference['removed'] + difference['revised'])


def compare_snapshots(base, target, *, identity_changes=None):
    before, after = snapshot_ref(base), snapshot_ref(target)
    changes = identity_changes if identity_changes is not None else dict(
        profile='cospace.synthetic-identity-changes/0.1', data_kind='synthetic', base=before, target=after, events=[])
    identity = validate_identity_changes(changes, base, target)
    sections = {key: _difference(base[key], target[key])
                for key in ('entities', 'geometry', 'relations', 'connections', 'observations', 'evidence', 'sources')}
    affected = set()
    evidence, sources = _changed_ids(sections['evidence']), _changed_ids(sections['sources'])
    for key in ('entities', 'geometry', 'relations', 'connections', 'observations'):
        changed = _changed_ids(sections[key])
        for row in base[key] + target[key]:
            if (row['id'] in changed or evidence.intersection(row['evidence_ids'])
                    or (key == 'observations' and row['source_id'] in sources)):
                affected.update(_subjects(key, row))
    return dict(profile='cospace.synthetic-snapshot-changes/0.1', data_kind='synthetic',
                base=before, target=after, sections=sections, identity=identity,
                affected_entity_ids=sorted(affected), assessment='unverified', real_release_ready=False,
                limitations=['description_changes_not_proven_physical_changes', 'affected_ids_not_a_rebuild_plan',
                             'no_automatic_identity_matching_or_adoption', 'no_navigation_or_traversability'])
