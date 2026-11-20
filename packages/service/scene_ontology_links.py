"""Consumer-owned definition references for existing, fixed model objects.

Authorization belongs to BusinessAccess. A link is an explicit classification
claim; it does not convert legacy properties or certify an ontology instance.
"""
from contextlib import closing, nullcontext
from datetime import datetime, timezone
from hashlib import sha256
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import sqlite3

from packages.ontology.kernel import Catalog, canonical_bytes
from packages.service.ontology_definition_workbench import DefinitionWorkbench
from packages.lifecycle.preview_control_lock import mutation_guard
from packages.service.scene_ontology_validation import validate_link_properties, validate_link_relations


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
        contents = model.objects() if model.manifest.get('semantic_annotation') else {'objects': []}
        objects = contents['objects']
        return {'space_id': space_id, 'candidate_id': candidate_id, 'source_sha256': digest,
                'frame_id': model.manifest['frame_id'], 'unit': contents.get('unit'), 'axes': model.manifest.get('axes'),
                'source_model_sha256': model.manifest['members']['spatial.npz']['sha256'], 'objects': objects, 'relations': contents.get('relations', [])}

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
                                            for key, value in module['concepts'].items()],
                               'relations': [{'relation_id': key, **value} for key, value in module['relations'].items()]})
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

    def fixed_snapshot(self, source, revision):
        require(type(revision) is int and 0 <= revision <= 2**63 - 1)
        if revision == 0:
            return {'revision': 0, 'source_sha256': source['source_sha256'], 'links': [], 'relation_links': []}
        require(self.path.is_file(), 'link_revision_not_found')
        # Querying an old revision must not create or migrate a consumer store.
        with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
            row = connection.execute('SELECT payload,digest FROM link_snapshots WHERE scope=? AND revision=?',
                                     (self.scope(source), revision)).fetchone()
        require(row is not None, 'link_revision_not_found')
        require(len(row[0]) <= 8_388_608 and sha256(row[0]).hexdigest() == row[1], 'link_store_integrity')
        value = json.loads(row[0])
        require(value['revision'] == revision, 'link_store_integrity')
        require(value['source_sha256'] == source['source_sha256'], 'link_source_changed')
        for link in value['links']:
            concept_definition(link['bundle'], link['reference'], link['concept_id'])
        return value

    def query(self, source, values):
        from packages.service.scene_ontology_query import query_object
        require({'space_id', 'candidate_id', 'object_id', 'revision'} <= set(values)
                and set(values) <= {'space_id', 'candidate_id', 'object_id', 'revision', 'at'})
        require(type(values['revision']) is str and re.fullmatch(r'0|[1-9][0-9]{0,18}', values['revision']) is not None)
        require(values['space_id'] == source['space_id'] and values['candidate_id'] == source['candidate_id'], 'link_source_changed')
        snapshot = self.fixed_snapshot(source, int(values['revision']))
        return query_object(source, snapshot, values['object_id'], values.get('at'))

    def read(self, source):
        with closing(self.connect()) as connection:
            value = self.head(connection, self.scope(source), source)
        return {**value, 'profile': 'cospace.scene-ontology-links/0.1',
                'space_id': source['space_id'], 'candidate_id': source['candidate_id'],
                'objects': [{'object_id': o['object_id'], 'name': o['properties'].get('name', o['object_id'])}
                            for o in source['objects']],
                'relations': source.get('relations', []), 'relation_links': value.get('relation_links', []),
                'relation_report': validate_link_relations(source, value),
                'options': self.options(), 'instance_validation': 'attributes_checked' if value['links'] else 'not_performed',
                'instance_report': validate_link_properties(source, value), 'included_in_publication': False}

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
        if body.get('action') in ('relation_set', 'relation_remove'):
            return self._change_relation(source, body)
        fields = {'action', 'space_id', 'candidate_id', 'source_sha256', 'object_id', 'expected_revision', 'request_id'}
        require(type(body.get('action')) is str and body['action'] in ('set', 'remove', 'properties'))
        if body['action'] == 'set':
            fields |= {'reference', 'concept_id'}
            if 'reset_properties' in body:
                require(type(body['reset_properties']) is bool)
                fields.add('reset_properties')
        if body['action'] == 'properties':
            fields |= {'properties', 'valid_time', 'evidence_note'}
        require(set(body) == fields)
        if body['action'] == 'properties':
            self.check_properties(body)
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
            if body['action'] == 'properties':
                require(old is not None, 'link_not_found')
                link = deepcopy(old)
                link.update(instance_properties=body['properties'], instance_valid_time=body['valid_time'],
                            evidence_note=body['evidence_note'], properties_updated_by=self.actor,
                            properties_updated_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
                changed = any(old.get(k) != link[k] for k in ('instance_properties', 'instance_valid_time', 'evidence_note'))
            else:
                changed = old is not None if link is None else old is None or any(old[k] != link[k] for k in ('reference', 'concept_id'))
                if changed and old is not None and link is not None:
                    require('instance_properties' not in old or body.get('reset_properties') is True, 'link_attributes_present')
            if changed:
                require(not any(body['object_id'] in (item['source_id'], item['target_id']) for item in head.get('relation_links', []))
                        or body['action'] == 'properties', 'link_relations_present')
                links = [i for i in head['links'] if i['object_id'] != body['object_id']]
                if link:
                    links.append(link)
                head = {'revision': head['revision'] + 1, 'source_sha256': source['source_sha256'],
                        'links': sorted(links, key=lambda i: i['object_id']),
                        'relation_links': head.get('relation_links', []), 'updated_by': self.actor,
                        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}
                raw = canonical_bytes(head)
                require(len(raw) <= 8_388_608, 'link_size_budget')
                # Recompute from the fixed closure; invalid intermediate claims
                # remain editable drafts, never masquerade as validated instances.
                validate_link_properties(source, head)
                connection.execute('INSERT INTO link_snapshots VALUES(?,?,?,?)', (scope, head['revision'], raw, sha256(raw).hexdigest()))
            result = {'revision': head['revision'], 'changed': changed, 'object_id': body['object_id']}
            connection.execute('INSERT INTO link_requests VALUES(?,?,?,?)', (scope, body['request_id'], fingerprint, canonical_bytes(result)))
            return result

    @staticmethod
    def check_properties(body):
        properties = body['properties']
        require(type(properties) is dict and len(properties) <= 128)
        require(type(body['evidence_note']) is str and 1 <= len(body['evidence_note'].strip()) <= 2000)
        period = body['valid_time']
        require(period is None or type(period) is dict and set(period) == {'start', 'end'}
                and type(period['start']) is str and len(period['start']) <= 40
                and (period['end'] is None or type(period['end']) is str and len(period['end']) <= 40))
        for key, prop in properties.items():
            require(type(key) is str and re.fullmatch('[a-z][a-z0-9_-]{0,63}', key) is not None)
            require(type(prop) is dict and 'value' in prop and set(prop) <= {'value', 'unit', 'quantity'})
            value = prop['value']
            require(type(value) in (str, int, float, bool))
            require(type(value) is not str or len(value) <= 2000)
            require(type(value) is not float or math.isfinite(value))
            require(type(value) is not int or value.bit_length() <= 1023)
            for field in ('unit', 'quantity'):
                if field in prop:
                    require(type(prop[field]) is str and 1 <= len(prop[field]) <= 80)


    def _change_relation(self, source, body):
        fields = {'action', 'space_id', 'candidate_id', 'source_sha256', 'relation_id', 'expected_revision', 'request_id'}
        if body['action'] == 'relation_set':
            fields |= {'reference', 'definition_id', 'valid_time', 'evidence_note', 'direction'}
        require(set(body) == fields)
        require(body['space_id'] == source['space_id'] and body['candidate_id'] == source['candidate_id'], 'link_source_changed')
        require(body['source_sha256'] == source['source_sha256'], 'link_source_changed')
        require(type(body['expected_revision']) is int and body['expected_revision'] >= 0)
        require(type(body['request_id']) is str and re.fullmatch('[a-f0-9]{32}', body['request_id']) is not None)
        require(type(body['relation_id']) is str)
        original = next((item for item in source.get('relations', []) if item['relation_id'] == body['relation_id']), None)
        require(original is not None, 'relation_not_found')
        link = None
        if body['action'] == 'relation_set':
            require(body['direction'] in ('forward', 'reverse'))
            self.check_properties({'properties': {}, 'valid_time': body['valid_time'], 'evidence_note': body['evidence_note']})
            require(body['valid_time'] is not None)
            require(type(body['definition_id']) is str and re.fullmatch('[a-z][a-z0-9_]{0,63}', body['definition_id']) is not None)
            fixed = self.definitions.service.read_release(self.workspace_scope, self.actor, body['reference'])
            module = next(item for item in fixed['bundle']['modules'] if item['module_id'] == fixed['reference']['module_id'])
            require(body['definition_id'] in module['relations'], 'relation_definition_not_found')
            link = {'relation_id': body['relation_id'], 'source_id': original['source_id' if body['direction'] == 'forward' else 'target_id'],
                    'target_id': original['target_id' if body['direction'] == 'forward' else 'source_id'], 'direction': body['direction'],
                    'reference': fixed['reference'], 'definition_id': body['definition_id'], 'bundle': fixed['bundle'],
                    'definition': module['relations'][body['definition_id']], 'valid_time': body['valid_time'],
                    'evidence_note': body['evidence_note'], 'epistemic_status': 'reported', 'linked_by': self.actor,
                    'linked_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}
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
            if link:
                linked = {item['object_id'] for item in head['links']}
                require(link['source_id'] in linked and link['target_id'] in linked, 'relation_endpoints_unlinked')
            previous = head.get('relation_links', [])
            old = next((item for item in previous if item['relation_id'] == body['relation_id']), None)
            changed = old is not None if link is None else old is None or any(old[key] != link[key] for key in ('reference', 'definition_id', 'valid_time', 'evidence_note', 'direction'))
            if changed:
                relations = [item for item in previous if item['relation_id'] != body['relation_id']]
                if link:
                    relations.append(link)
                head = {**head, 'revision': head['revision'] + 1, 'relation_links': sorted(relations, key=lambda item: item['relation_id']),
                        'updated_by': self.actor, 'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}
                raw = canonical_bytes(head)
                require(len(raw) <= 8_388_608, 'link_size_budget')
                validate_link_relations(source, head)
                connection.execute('INSERT INTO link_snapshots VALUES(?,?,?,?)', (scope, head['revision'], raw, sha256(raw).hexdigest()))
            result = {'revision': head['revision'], 'changed': changed, 'relation_id': body['relation_id']}
            connection.execute('INSERT INTO link_requests VALUES(?,?,?,?)', (scope, body['request_id'], fingerprint, canonical_bytes(result)))
            return result
