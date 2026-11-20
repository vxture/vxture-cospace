"""Host-owned admission and immutable projection of one explicit semantic revision."""
from copy import deepcopy
from hashlib import sha256
import hmac
import json
from pathlib import Path
import secrets
import uuid

from jsonschema import Draft202012Validator
from packages.ontology.kernel import Catalog, canonical_bytes
from packages.service.scene_ontology_links import concept_definition, require
from packages.service.scene_ontology_query import timestamp
from packages.service.scene_ontology_validation import validate_link_properties, validate_link_relations


PROFILE = 'cospace.object-semantic-artifact/0.1'
MANIFEST = 'semantic-artifact.json'
MEMBERS = ('object-index.json', 'definitions.json', 'claims.json', 'validation.json')
MAX_BYTES = 8_388_608
SCHEMA = json.loads((Path(__file__).resolve().parents[2] /
    'contracts/schemas/object-semantic-artifact-v0.1.schema.json').read_bytes())


def digest(raw):
    return sha256(raw).hexdigest()


def validate_selection(value, *, preflight=False):
    fields = {'consumer_revision', 'source_manifest_sha256'} | (set() if preflight else {'snapshot_sha256'})
    require(type(value) is dict and set(value) == fields, 'semantic_selection_invalid')
    require(type(value['consumer_revision']) is int and 0 < value['consumer_revision'] <= 2**63-1,
            'semantic_selection_invalid')
    import re
    for key in fields - {'consumer_revision'}:
        require(type(value[key]) is str and re.fullmatch('[a-f0-9]{64}', value[key]) is not None,
                'semantic_selection_invalid')


def admit(source, snapshot):
    require(type(snapshot['revision']) is int and snapshot['revision'] > 0, 'semantic_empty_revision')
    require(snapshot['source_sha256'] == source['source_sha256'], 'link_source_changed')
    objects = {item['object_id']: item for item in source['objects']}
    require(len(objects) == len(source['objects']), 'semantic_duplicate_object')
    links = snapshot['links']
    linked = {item['object_id'] for item in links}
    require(links and len(linked) == len(links) and linked <= objects.keys(), 'semantic_object_binding')
    modules = {}
    mappings = snapshot.get('relation_links', [])
    original = {item['relation_id']: item for item in source.get('relations', [])}
    require(len(original) == len(source.get('relations', [])), 'semantic_relation_binding')
    require(len({item['relation_id'] for item in mappings}) == len(mappings), 'semantic_relation_binding')
    for item in links + mappings:
        for module in item['bundle']['modules']:
            key = module['module_id']
            require(key not in modules or canonical_bytes(modules[key]) == canonical_bytes(module),
                    'semantic_definition_conflict')
            modules[key] = module
        require(type(item.get('evidence_note')) is str and bool(item['evidence_note'].strip()),
                'semantic_evidence_missing')
        timestamp(item['linked_at'])
        if item.get('properties_updated_at'):
            timestamp(item['properties_updated_at'])
    catalog = Catalog(list(modules.values()))
    refs = [entry['reference'] for entry in catalog.describe()['modules']]
    for link in links:
        require(link['reference'] in refs, 'semantic_definition_binding')
        concept_definition(link['bundle'], link['reference'], link['concept_id'])
    for mapping in mappings:
        relation = original.get(mapping['relation_id'])
        require(relation is not None and mapping['direction'] in ('forward', 'reverse'), 'semantic_relation_binding')
        endpoints = [relation['source_id'], relation['target_id']]
        if mapping['direction'] == 'reverse':
            endpoints.reverse()
        require(endpoints == [mapping['source_id'], mapping['target_id']] and set(endpoints) <= linked,
                'semantic_relation_binding')
        require(mapping['reference'] in refs, 'semantic_definition_binding')
    attributes = validate_link_properties(source, snapshot)
    require(attributes['valid'], 'semantic_attributes_invalid')
    relations = validate_link_relations(source, snapshot) if mappings else None
    require(relations is None or relations['valid'], 'semantic_relations_invalid')
    coverage = dict(scope='linked_objects_and_mapped_relations', objects_total=len(objects),
        linked_objects=len(linked), unlinked_objects=len(objects)-len(linked),
        relations_total=len(original), mapped_relations=len(mappings), unmapped_relations=len(original)-len(mappings))
    return catalog, coverage, attributes, relations


def preflight(service, source, selection):
    validate_selection(selection, preflight=True)
    require(selection['source_manifest_sha256'] == source['source_sha256'], 'link_source_changed')
    snapshot = service.fixed_snapshot(source, selection['consumer_revision'])
    _, coverage, attributes, relations = admit(source, snapshot)
    return dict(selection, snapshot_sha256=digest(canonical_bytes(snapshot))), {
        'coverage': coverage, 'attribute_report': attributes,
        'relation_report': relations, 'mapped_relation_validation': 'passed' if relations else 'not_applicable'}


def freeze(service, source, selection, generated_at):
    validate_selection(selection)
    accepted, _ = preflight(service, source, {k:v for k,v in selection.items() if k != 'snapshot_sha256'})
    require(accepted == selection, 'semantic_snapshot_changed')
    snapshot = service.fixed_snapshot(source, selection['consumer_revision'])
    catalog, coverage, attributes, relations = admit(source, snapshot)
    timestamp(generated_at)
    artifact_id = 'semantic-' + uuid.uuid4().hex
    secret = secrets.token_bytes(32)
    def actor(value):
        return 'actor-' + hmac.new(secret, value.encode(), 'sha256').hexdigest()
    def project(item, fields):
        result = {key:deepcopy(item[key]) for key in fields if key in item}
        for key in ('linked_by', 'properties_updated_by'):
            if key in item:
                result[key] = actor(item[key])
        return result
    objects = [{key:deepcopy(item[key]) for key in ('object_id', 'anchor_m', 'evidence') if key in item} |
               {'name':item['properties'].get('name', item['object_id'])} for item in source['objects']]
    index = {key:deepcopy(source[key]) for key in ('space_id','candidate_id','source_sha256',
        'source_model_sha256','frame_id','unit','axes') if key in source}
    index.update(objects=objects, relations=[{k:item[k] for k in ('relation_id','source_id','target_id')}
        for item in source.get('relations', [])])
    link_fields = ('object_id','reference','concept_id','instance_properties','instance_valid_time',
                   'evidence_note','linked_at','properties_updated_at')
    relation_fields = ('relation_id','source_id','target_id','direction','reference','definition_id',
                       'valid_time','evidence_note','epistemic_status','linked_at')
    claims = {'revision':snapshot['revision'], 'source_sha256':snapshot['source_sha256'],
        'links':[project(item, link_fields) for item in snapshot['links']],
        'relation_links':[project(item, relation_fields) for item in snapshot.get('relation_links', [])]}
    if snapshot.get('updated_at'):
        claims['updated_at'] = snapshot['updated_at']
    files = {'object-index.json':canonical_bytes(index), 'definitions.json':canonical_bytes(catalog.export()),
             'claims.json':canonical_bytes(claims)}
    validation = {'input_sha256':{name:digest(raw) for name,raw in files.items()},
        'attributes':attributes, 'mapped_relations':relations,
        'mapped_relation_validation':'passed' if relations else 'not_applicable'}
    files['validation.json'] = canonical_bytes(validation)
    manifest = dict(profile=PROFILE, artifact_id=artifact_id, revision=1,
        workspace_scope='scope-' + digest(service.workspace_scope.encode()), space_id=source['space_id'],
        candidate_id=source['candidate_id'], consumer_revision=snapshot['revision'],
        snapshot_sha256=selection['snapshot_sha256'], source_manifest_sha256=source['source_sha256'],
        source_model_sha256=source['source_model_sha256'], generated_at=generated_at, coverage=coverage,
        capabilities=dict(object_semantic_query=True, geometry_evidence_reverification=False,
            robot_navigation=False, robot_task_execution=False),
        assessment=dict(attribute_validation='passed', mapped_relation_validation='passed' if relations else 'not_applicable',
            professional_review='not_performed', field_verification='not_performed'),
        evidence_policy=dict(model='external_reference', attachments='references_only',
            audit_identity_policy='artifact_scoped_pseudonyms'),
        members={name:dict(sha256=digest(raw), bytes=len(raw), media_type='application/json') for name,raw in files.items()})
    Draft202012Validator(SCHEMA).validate(manifest)
    files[MANIFEST] = canonical_bytes(manifest)
    require(sum(map(len, files.values())) <= MAX_BYTES, 'semantic_size_budget')
    return manifest, files


def verify_publication(record, root):
    """Fail closed for declared artifacts; legacy publications need no new files."""
    declared = record.get('semantic_artifact')
    if declared is None:
        require('semantic_selection' not in record and MANIFEST not in record['files'], 'semantic_publication_binding')
        return None
    require(type(declared) is dict, 'semantic_publication_binding')
    require(declared.get('path') == MANIFEST and declared.get('profile') == PROFILE,
            'semantic_publication_binding')
    require(set(MEMBERS + (MANIFEST,)) <= record['files'].keys(), 'semantic_publication_binding')
    manifest = json.loads((root / MANIFEST).read_bytes())
    require(not list(Draft202012Validator(SCHEMA).iter_errors(manifest)), 'semantic_manifest_invalid')
    timestamp(manifest['generated_at'])
    require(manifest['artifact_id'] == declared['artifact_id'] and manifest['space_id'] == record['space_id']
        and manifest['candidate_id'] == record['candidate_id']
        and manifest['source_manifest_sha256'] == record['model_manifest_sha256']
        and manifest['source_model_sha256'] == record['source_model_sha256']
        and manifest['workspace_scope'] == record['semantic_workspace_scope'], 'semantic_publication_binding')
    expected = dict(consumer_revision=manifest['consumer_revision'],
        source_manifest_sha256=manifest['source_manifest_sha256'], snapshot_sha256=manifest['snapshot_sha256'])
    require(expected == record['semantic_selection'], 'semantic_publication_binding')
    total = len((root / MANIFEST).read_bytes())
    for name,member in manifest['members'].items():
        raw = (root / name).read_bytes()
        total += len(raw)
        require(len(raw) == member['bytes'] and digest(raw) == member['sha256'], 'semantic_member_integrity')
    require(total <= MAX_BYTES, 'semantic_size_budget')
    return manifest
