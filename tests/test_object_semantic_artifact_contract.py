"""Public manifest shape; cross-member admission is implemented in B06b."""
from copy import deepcopy
import json
from pathlib import Path
from datetime import datetime

from jsonschema import Draft202012Validator, FormatChecker
import pytest


SCHEMA = json.loads(Path('contracts/schemas/object-semantic-artifact-v0.1.schema.json').read_bytes())
FORMATS = FormatChecker()


@FORMATS.checks('date-time', raises=ValueError)
def utc_datetime(value):
    if not isinstance(value,str):
        return True
    return value.endswith('Z') and datetime.fromisoformat(value.replace('Z','+00:00')) is not None


VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FORMATS)


def manifest(mapped=False):
    return dict(profile='cospace.object-semantic-artifact/0.1', artifact_id='semantic-'+'a'*32,
        revision=1, workspace_scope='workspace', space_id='scene', candidate_id='build',
        consumer_revision=4, snapshot_sha256='a'*64, source_manifest_sha256='b'*64,
        source_model_sha256='c'*64, generated_at='2026-11-20T10:00:00Z',
        coverage=dict(scope='linked_objects_and_mapped_relations', objects_total=2,
            linked_objects=1, unlinked_objects=1, relations_total=1,
            mapped_relations=int(mapped), unmapped_relations=int(not mapped)),
        capabilities=dict(object_semantic_query=True, geometry_evidence_reverification=False,
            robot_navigation=False, robot_task_execution=False),
        assessment=dict(attribute_validation='passed', mapped_relation_validation='passed' if mapped else 'not_applicable',
            professional_review='not_performed', field_verification='not_performed'),
        evidence_policy=dict(model='external_reference', attachments='references_only',
            audit_identity_policy='artifact_scoped_pseudonyms'),
        members={name:dict(sha256='d'*64, bytes=100, media_type='application/json')
            for name in ('object-index.json','definitions.json','claims.json','validation.json')})


def test_manifest_accepts_explicit_partial_coverage_and_no_relation_applicability():
    Draft202012Validator.check_schema(SCHEMA)
    VALIDATOR.validate(manifest())
    VALIDATOR.validate(manifest(True))


@pytest.mark.parametrize('field,value', [('consumer_revision',0), ('consumer_revision',True),
    ('consumer_revision','latest'), ('source_model_sha256','bad'),
    ('generated_at','2026-02-30T00:00:00Z'), ('generated_at','2026-11-20T10:00:00+00:00')])
def test_manifest_rejects_ambiguous_fixed_binding(field,value):
    value_doc=manifest();value_doc[field]=value
    assert list(VALIDATOR.iter_errors(value_doc))


def test_manifest_rejects_missing_closure_unknown_members_and_unearned_capabilities():
    for change in ('missing','unknown','navigation','field_verified','oversized'):
        value=deepcopy(manifest())
        if change=='missing':del value['members']['definitions.json']
        if change=='unknown':value['members']['sessions.sqlite3']=value['members']['claims.json']
        if change=='navigation':value['capabilities']['robot_navigation']=True
        if change=='field_verified':value['assessment']['field_verification']='passed'
        if change=='oversized':value['members']['claims.json']['bytes']=8388609
        assert list(VALIDATOR.iter_errors(value)),change
