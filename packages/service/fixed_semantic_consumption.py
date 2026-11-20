"""Identical fixed semantic admission and query for online and offline consumers."""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator
from packages.ontology.kernel import Catalog
from packages.service.object_semantic_artifact import PROFILE, MANIFEST, MEMBERS, MAX_BYTES, SCHEMA, admit, digest
from packages.service.scene_ontology_links import require, concept_definition
from packages.service.scene_ontology_query import timestamp, query_object


def decode(raw):
    def unique(pairs):
        value = {}
        for key,item in pairs:
            require(key not in value, 'semantic_duplicate_key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


class FixedSemantics:
    def __init__(self, record, files, model_manifest, model_objects, model_relations):
        require(set(files) == set(MEMBERS + (MANIFEST,)), 'semantic_members_invalid')
        require(all(type(raw) is bytes for raw in files.values())
                and sum(map(len, files.values())) <= MAX_BYTES, 'semantic_size_budget')
        declared = record.get('semantic_artifact')
        require(type(declared) is dict and declared.get('path') == MANIFEST
                and declared.get('profile') == PROFILE, 'semantic_publication_binding')
        for name,raw in files.items():
            ref = record['files'].get(name, {})
            require(ref.get('sha256') == digest(raw) and ref.get('bytes') == len(raw), 'semantic_member_integrity')
        manifest = decode(files[MANIFEST])
        require(not list(Draft202012Validator(SCHEMA).iter_errors(manifest)), 'semantic_manifest_invalid')
        timestamp(manifest['generated_at'])
        require(manifest['artifact_id'] == declared.get('artifact_id')
            and manifest['space_id'] == record.get('space_id')
            and manifest['candidate_id'] == record['candidate_id']
            and manifest['workspace_scope'] == record.get('semantic_workspace_scope')
            and manifest['source_manifest_sha256'] == record['model_manifest_sha256']
            and manifest['source_model_sha256'] == record['source_model_sha256'], 'semantic_publication_binding')
        require(record.get('semantic_selection') == dict(consumer_revision=manifest['consumer_revision'],
            source_manifest_sha256=manifest['source_manifest_sha256'],snapshot_sha256=manifest['snapshot_sha256']),
            'semantic_publication_binding')
        for name in MEMBERS:
            ref = manifest['members'][name]
            require(ref['sha256'] == digest(files[name]) and ref['bytes'] == len(files[name]), 'semantic_member_integrity')
        source = decode(files['object-index.json'])
        claims = decode(files['claims.json'])
        require(source['space_id'] == manifest['space_id'] and source['candidate_id'] == manifest['candidate_id']
            and source['source_sha256'] == manifest['source_manifest_sha256']
            and source['source_model_sha256'] == manifest['source_model_sha256']
            and source['frame_id'] == model_manifest['frame_id']
            and claims['revision'] == manifest['consumer_revision']
            and claims['source_sha256'] == source['source_sha256'], 'semantic_source_binding')
        expected = [{key:deepcopy(item[key]) for key in ('object_id','anchor_m','evidence') if key in item} |
            {'name':item['properties'].get('name',item['object_id'])} for item in model_objects]
        require(source['objects'] == expected, 'semantic_object_index_binding')
        require(source['relations'] == [{key:item[key] for key in ('relation_id','source_id','target_id')}
            for item in model_relations], 'semantic_relation_index_binding')
        require(source.get('unit') == 'm' and source.get('axes') == model_manifest.get('axes'), 'semantic_frame_binding')
        source = deepcopy(source)
        source['objects'] = [dict(item,properties={'name':item['name']}) for item in source['objects']]
        catalog = Catalog.from_bytes(files['definitions.json'])
        refs = {entry['reference']['module_id']:entry['reference'] for entry in catalog.describe()['modules']}
        module_map = {module['module_id']:module for module in catalog.export()['modules']}
        snapshot = deepcopy(claims)
        for link in snapshot['links'] + snapshot['relation_links']:
            module_id = link['reference']['module_id']
            require(refs.get(module_id) == link['reference'], 'semantic_definition_binding')
            link['bundle'] = catalog.export(module_id)
            if 'concept_id' in link:
                link['definition'] = concept_definition(link['bundle'],link['reference'],link['concept_id'])
            else:
                link['definition'] = module_map[module_id]['relations'][link['definition_id']]
        _, coverage, attributes, relations = admit(source, snapshot)
        require(coverage == manifest['coverage'], 'semantic_coverage_invalid')
        assessment = 'passed' if relations else 'not_applicable'
        require(manifest['assessment']['mapped_relation_validation'] == assessment, 'semantic_report_binding')
        validation = decode(files['validation.json'])
        require(validation['input_sha256'] == {name:digest(files[name]) for name in MEMBERS if name != 'validation.json'},
                'semantic_report_binding')
        require(validation['attributes'] == attributes and validation['mapped_relations'] == relations
                and validation['mapped_relation_validation'] == assessment, 'semantic_report_binding')
        self.record, self.manifest, self.source, self.snapshot = record, manifest, source, snapshot

    def summary(self):
        return dict(profile='cospace.publication-semantics/0.1', publication_id=self.record['id'],
            state='included', artifact_id=self.manifest['artifact_id'], revision=self.manifest['consumer_revision'],
            source_sha256=self.manifest['source_manifest_sha256'], space_id=self.manifest['space_id'],
            candidate_id=self.manifest['candidate_id'], coverage=deepcopy(self.manifest['coverage']),
            assessment=deepcopy(self.manifest['assessment']), capabilities=deepcopy(self.manifest['capabilities']),
            evidence_policy=deepcopy(self.manifest['evidence_policy']),
            objects=[{'object_id':item['object_id'],'name':item['name']} for item in self.source['objects']])

    def query(self, object_id, at=None):
        result = query_object(self.source,self.snapshot,object_id,at)
        # The artifact promises evidence references, not re-verification of geometry bytes.
        result['model_location'] = dict(available=False,preview_available=False,
            reason='geometry_evidence_external_reference', reference=deepcopy(next(item for item in self.source['objects']
                if item['object_id'] == object_id)), geographic_location=dict(available=False,reason='geographic_handoff_not_connected'))
        return dict(result,profile='cospace.publication-semantic-object/0.1',publication_id=self.record['id'],
            artifact_id=self.manifest['artifact_id'],included_in_publication=True,
            relation_report=None if not self.snapshot['relation_links'] else result['relation_report'])


def read_fixed(record, model):
    if not record.get('semantic_artifact'):
        require('semantic_selection' not in record and MANIFEST not in record['files'], 'semantic_publication_binding')
        return None
    files = {}
    for name in MEMBERS + (MANIFEST,):
        with (model.root/name).open('rb') as stream:
            files[name] = stream.read(MAX_BYTES + 1)
    objects = model.semantic_snapshot['objects'] if model.semantic_snapshot else []
    fixed = FixedSemantics(record,files,model.manifest,objects,model.objects().get('relations',[]))
    return fixed


def not_included(record):
    return dict(profile='cospace.publication-semantics/0.1',publication_id=record['id'],state='not_included',objects=[])
