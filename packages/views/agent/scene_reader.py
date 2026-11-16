"""SG4 preparation: fixed synthetic subset queries, without HTTP or publication."""
from copy import deepcopy

from pydantic import TypeAdapter

from packages.spatial.scene_graph import Identity
from packages.views.agent.scene_subset import read_scene_subset

IDENTITY = TypeAdapter(Identity)


class SceneSubsetReader:
    """Package-local results never imply full scene coverage or device reachability."""

    def __init__(self, package, expected_source, *, source_document=None):
        self._graph, report = read_scene_subset(package, expected_source, source_document=source_document)
        self._entities = {row['id']: row for row in self._graph['entities']}
        self._requested = frozenset(report['requested_ids'])
        self._context = dict(source=deepcopy(expected_source), subset_snapshot_id=self._graph['snapshot_id'],
                             frame=deepcopy(self._graph['frame']), validation=report,
                             query_scope='package_only', observation_resolution='not_applied')

    @property
    def context(self):
        return deepcopy(self._context)

    def _result(self, outcome, items, **extra):
        return deepcopy(dict(outcome=outcome, items=items, context=self._context, **extra))

    def list_entities(self, *, type_id=None):
        if type_id is not None:
            IDENTITY.validate_python(type_id)
        rows = [row for row in self._entities.values() if type_id is None or row['type_id'] == type_id]
        return self._result('found' if rows else 'no_match', sorted(rows, key=lambda row: row['id']))

    def entity(self, identity):
        IDENTITY.validate_python(identity)
        if identity not in self._entities:
            return self._result('out_of_scope', [])
        entity = self._entities[identity]
        item = dict(entity=entity,
                    geometry=[g for g in self._graph['geometry'] if g['id'] in entity['geometry_ids']],
                    relations=[r for r in self._graph['relations']
                               if identity in (r['source_id'], r['target_id'])],
                    observations=[o for o in self._graph['observations'] if o['entity_id'] == identity])
        return self._result('found', [item])

    def connections(self, identity):
        IDENTITY.validate_python(identity)
        if identity not in self._entities:
            return self._result('out_of_scope', [], incident_connections_complete=False)
        rows = [row for row in self._graph['connections'] if row['connector_id'] == identity
                or any(port['space_id'] == identity for port in row['ports'])]
        complete = (self._context['validation']['source_content_verified'] and identity in self._requested)
        return self._result('found' if rows else 'no_match', sorted(rows, key=lambda row: row['id']),
                            incident_connections_complete=complete)
