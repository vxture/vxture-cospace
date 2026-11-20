"""Consumer-owned definition references for existing, fixed model objects.

Authorization belongs to BusinessAccess. A link is an explicit classification
claim; it does not convert legacy properties or certify an ontology instance.
"""
from contextlib import closing, nullcontext
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from packages.ontology.kernel import Catalog, canonical_bytes
from packages.service.ontology_definition_workbench import DefinitionWorkbench
from packages.lifecycle.preview_control_lock import mutation_guard


class SceneLinkError(ValueError):
    pass


def require(condition, code='invalid_link_request'):
    if not condition:
        raise SceneLinkError(code)


def concept_definition(bundle, reference, concept_id):
    catalog = Catalog.from_bytes(canonical_bytes(bundle))
    modules = catalog.export()['modules']
    entry = next((e for e in catalog.describe()['modules'] if e['reference'] == reference), None)
    require(entry is not None, 'link_definition_integrity')
    concepts = {m['module_id'] + ':' + key: value for m in modules for key, value in m['concepts'].items()}
    key = reference['module_id'] + ':' + concept_id
    require(key in concepts, 'concept_not_found')
    definition = concepts[key]
    chain = []
    while key:
        chain.append(concepts[key])
        key = concepts[key].get('parent')
    properties = {}
    for item in reversed(chain):
        properties.update(item['properties'])
    return {**definition, 'effective_properties': properties}


class SceneOntologyLinks:
    def __init__(self, root, workspace_scope, actor, jobs):
        self.path = Path(root) / 'scene-ontology-links.sqlite3'
        self.workspace_scope, self.actor, self.jobs = workspace_scope, actor, jobs
        self.definitions = DefinitionWorkbench(root, workspace_scope, actor, False)

    def source(self, space_id, candidate_id):
        # Caller has authorized both scene and candidate before this I/O.
        model = self.jobs.model(candidate_id)
        require(model.manifest['space_id'] == space_id and model.manifest['id'] == candidate_id,
                'link_source_changed')
        digest = sha256((model.root / 'model.json').read_bytes()).hexdigest()
        objects = model.objects()['objects'] if model.manifest.get('semantic_annotation') else []
        return {'space_id': space_id, 'candidate_id': candidate_id, 'source_sha256': digest,
                'frame_id': model.manifest['frame_id'], 'objects': objects}

    def options(self):
        result = []
        for entry in self.definitions.released_library()['modules']:
            identity = entry['reference']['module_id']
            for release in self.definitions.service.list_releases(self.workspace_scope, self.actor, identity):
                fixed = self.definitions.service.read_release(self.workspace_scope, self.actor, release['reference'])
                module = next(m for m in fixed['bundle']['modules'] if m['module_id'] == identity)
                result.append({**release, 'title': module['title'], 'maturity': module['status'],
                               'concepts': [{'concept_id': key, 'title': value['title'],
                                             'definition': value['definition']}
                                            for key, value in module['concepts'].items()]})
        return result

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute('CREATE TABLE IF NOT EXISTS link_snapshots(scope TEXT NOT NULL,revision INTEGER NOT NULL,payload BLOB NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(scope,revision))')
        connection.execute('CREATE TABLE IF NOT EXISTS link_requests(scope TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,result BLOB NOT NULL,PRIMARY KEY(scope,request_id))')
        connection.commit()
        return connection

    def scope(self, source):
        return sha256(canonical_bytes([self.workspace_scope, source['space_id'], source['candidate_id']])).hexdigest()

    @staticmethod
    def head(connection, scope, source):
        row = connection.execute('SELECT payload,digest FROM link_snapshots WHERE scope=? ORDER BY revision DESC LIMIT 1', (scope,)).fetchone()
        if row is None:
            return {'revision': 0, 'source_sha256': source['source_sha256'], 'links': []}
        require(len(row[0]) <= 8_388_608 and sha256(row[0]).hexdigest() == row[1], 'link_store_integrity')
        value = json.loads(row[0])
        require(value['source_sha256'] == source['source_sha256'], 'link_source_changed')
        for link in value['links']:
            concept_definition(link['bundle'], link['reference'], link['concept_id'])
        return value

    def read(self, source):
        with closing(self.connect()) as connection:
            value = self.head(connection, self.scope(source), source)
        return {**value, 'profile': 'cospace.scene-ontology-links/0.1',
                'space_id': source['space_id'], 'candidate_id': source['candidate_id'],
                'objects': [{'object_id': o['object_id'], 'name': o['properties'].get('name', o['object_id'])}
                            for o in source['objects']],
                'options': self.options(), 'instance_validation': 'not_performed', 'included_in_publication': False}

    def change(self, source, body):
        guard = mutation_guard(self.jobs.root.parent) if self.jobs is not None else nullcontext()
        with guard:
            if self.jobs is not None:
                try:
                    self.jobs.controls.require_active(source['space_id'], 'candidate:' + source['candidate_id'])
                except ValueError as exc:
                    if str(exc).startswith('lifecycle_') and str(exc).endswith('_new_use_blocked'):
                        raise SceneLinkError('link_source_inactive') from exc
                    raise
                fresh = self.source(source['space_id'], source['candidate_id'])
                require(fresh['source_sha256'] == source['source_sha256'], 'link_source_changed')
                source = fresh
            return self._change(source, body)

    def _change(self, source, body):
        fields = {'action', 'space_id', 'candidate_id', 'source_sha256', 'object_id', 'expected_revision', 'request_id'}
        require(type(body.get('action')) is str and body['action'] in ('set', 'remove'))
        if body['action'] == 'set':
            fields |= {'reference', 'concept_id'}
        require(set(body) == fields)
        require(body['space_id'] == source['space_id'] and body['candidate_id'] == source['candidate_id'], 'link_source_changed')
        require(type(body['object_id']) is str and any(o['object_id'] == body['object_id'] for o in source['objects']), 'object_not_found')
        require(type(body['expected_revision']) is int and body['expected_revision'] >= 0)
        require(type(body['request_id']) is str and re.fullmatch('[a-f0-9]{32}', body['request_id']) is not None)
        require(body['source_sha256'] == source['source_sha256'], 'link_source_changed')
        link = None
        if body['action'] == 'set':
            require(type(body['concept_id']) is str and re.fullmatch('[a-z][a-z0-9_]{0,63}', body['concept_id']) is not None)
            # No builtin fallback: candidates/drafts cannot become adopted releases.
            fixed = self.definitions.service.read_release(self.workspace_scope, self.actor, body['reference'])
            definition = concept_definition(fixed['bundle'], fixed['reference'], body['concept_id'])
            link = {'object_id': body['object_id'], 'reference': fixed['reference'], 'concept_id': body['concept_id'],
                    'bundle': fixed['bundle'], 'definition': definition,
                    'linked_by': self.actor, 'linked_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}
        scope = self.scope(source)
        fingerprint = sha256(canonical_bytes([self.actor, body])).hexdigest()
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            replay = connection.execute('SELECT fingerprint,result FROM link_requests WHERE scope=? AND request_id=?', (scope, body['request_id'])).fetchone()
            if replay:
                require(replay[0] == fingerprint, 'link_request_conflict')
                return json.loads(replay[1])
            head = self.head(connection, scope, source)
            require(head['revision'] == body['expected_revision'], 'link_revision_changed')
            old = next((i for i in head['links'] if i['object_id'] == body['object_id']), None)
            changed = old is not None if link is None else old is None or any(old[k] != link[k] for k in ('reference', 'concept_id'))
            if changed:
                links = [i for i in head['links'] if i['object_id'] != body['object_id']]
                if link:
                    links.append(link)
                head = {'revision': head['revision'] + 1, 'source_sha256': source['source_sha256'],
                        'links': sorted(links, key=lambda i: i['object_id']), 'updated_by': self.actor,
                        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}
                raw = canonical_bytes(head)
                require(len(raw) <= 8_388_608, 'link_size_budget')
                connection.execute('INSERT INTO link_snapshots VALUES(?,?,?,?)', (scope, head['revision'], raw, sha256(raw).hexdigest()))
            result = {'revision': head['revision'], 'changed': changed, 'object_id': body['object_id']}
            connection.execute('INSERT INTO link_requests VALUES(?,?,?,?)', (scope, body['request_id'], fingerprint, canonical_bytes(result)))
            return result
