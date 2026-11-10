"""Read-only service diagnostics from scoped metadata; never a synthetic probe."""
import json
import re
import sqlite3
from packages.service.preview_publications import PreviewPublications


def version_status(jobs, space):
    pubs = PreviewPublications(jobs)
    project = jobs.directory.read('space', space)['project_id']
    versions = []
    for path in sorted(pubs.root.glob('preview-*/publication.json')):
        record = json.loads(path.read_bytes())
        if not isinstance(record, dict):
            raise ValueError('service_version_metadata_invalid')
        if record.get('space_id') != space:
            continue
        # An invalid ownership association never becomes a serviceable version.
        identity = path.parent.name
        if record.get('project_id') != project or record.get('id') != identity or not re.fullmatch(r'preview-[a-f0-9]{16}', identity):
            raise ValueError('service_version_binding_invalid')
        try:
            lifecycle = pubs.distribution(identity)
            state = lifecycle['lifecycle_state']
            if state not in ('active', 'paused', 'retired'):
                state = 'unavailable'
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            state = 'unavailable'
        versions.append({'publication_id': identity, 'created_at': record.get('created_at'),
                         'state': state, 'realtime': 'unverified',
                         'replacement_publication_id': lifecycle.get('replacement_publication_id') if state == 'retired' else None})
    versions.sort(key=lambda value: (value['created_at'] or '', value['publication_id']), reverse=True)
    return {'state': 'observed', 'version_count': len(versions),
            'distributing_count': sum(v['state'] == 'active' for v in versions), 'versions': versions[:50]}


def assurance(jobs, space, report, configuration):
    try:
        releases = version_status(jobs, space)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        releases = {'state': 'unavailable', 'version_count': None, 'distributing_count': None, 'versions': []}
    checks = [
        {'key': 'integration', 'state': 'pass' if configuration['state'] == 'configured' else 'attention',
         'action': 'deployment'},
        {'key': 'publication', 'state': 'unknown' if releases['state'] == 'unavailable' else 'pass' if releases['distributing_count'] else 'attention',
         'action': 'publishing'},
        # Current S2S recordings do not provide a verified UTC observation clock.
        {'key': 'freshness', 'state': 'attention' if releases['distributing_count'] else 'unknown', 'action': 'evidence'},
        {'key': 'observation', 'state': 'attention' if report['coverage']['partial'] else 'pass', 'action': 'monitoring'},
    ]
    return {'checks': checks, 'releases': releases, 'basis': 'configuration_metadata_and_recorded_requests',
            'end_to_end_probe': False}
