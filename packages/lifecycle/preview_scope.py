"""Explicit space ownership; an absent space always means legacy/unassigned."""


def scope(directory, space_id=None):
    if space_id is None:
        return {}
    if directory is None:
        raise ValueError('space_directory_not_configured')
    record = directory.read('space', space_id)
    directory.read('project', record['project_id'])
    return {'space_id': record['id'], 'project_id': record['project_id']}


def match(record, ownership):
    if any(record.get(key) != ownership.get(key) for key in ('space_id', 'project_id')):
        raise ValueError('space_ownership_mismatch')


def owned(record):
    return {key: record[key] for key in ('space_id', 'project_id') if key in record}
