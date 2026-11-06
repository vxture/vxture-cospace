"""Generation provenance stays distinguishable from read time and runtime validity."""
import copy
import json
from pathlib import Path
import uuid

import pytest
from jsonschema import Draft202012Validator

from packages.data.delivery_report import ReportGeneration, generation_context
from packages.service.delivery import SavedDeliveryReader, DeliveryReportError


@pytest.fixture
def contextual(tmp_path):
    legacy = json.loads(Path('tests/fixtures/p2-delivery-audit-001/scenario.json').read_text(encoding='utf-8'))['scenarios']['clean']
    document = copy.deepcopy(legacy)
    document['schema_version'] = 'cospace.test-delivery-audit/0.2'
    document['generation'] = {
        'schema_version': 'cospace.delivery-generation/0.1', 'report_id': str(uuid.uuid4()),
        'producer': {'name': 'cospace.delivery-audit', 'version': '0.2'},
        'interval': {'started_at': '2026-10-27T00:00:00.000000Z', 'finished_at': '2026-10-27T00:00:00.100000Z',
                     'elapsed_ms': 100, 'clock': 'system_utc_untrusted', 'wall_end_before_start': False,
                     'consistency': 'independent_readonly_snapshots'},
        **generation_context(document, tmp_path / 'files', tmp_path / 'journal', 100)}
    path = tmp_path / 'report.json'
    def read(value):
        path.write_text(json.dumps(value), encoding='utf-8')
        binding = value['requested_binding']
        return SavedDeliveryReader(path).read(binding['scene_id'], binding['release_id'])
    return document, read


def test_new_context_and_legacy_read_time_are_distinct(contextual):
    document, read = contextual
    new = read(document)
    assert new['report']['generation'] == document['generation']
    assert new['source']['observed_at'] is None
    assert new['source']['read_at'] != document['generation']['interval']['finished_at']
    assert not new['report']['authorized'] and new['report']['validity'] == 'not_evaluated'
    legacy = copy.deepcopy(document)
    del legacy['generation']
    legacy['schema_version'] = 'cospace.test-delivery-audit/0.1'
    assert read(legacy)['report']['generation'] is None


@pytest.mark.parametrize('change', ['id', 'date', 'clock', 'elapsed', 'missing', 'extra', 'payload',
                                  'binding', 'component', 'control', 'legacy_claim', 'missing_generation'])
def test_invalid_or_detached_context_rejected(contextual, change):
    document, read = contextual
    generation = document['generation']
    if change == 'id': generation['report_id'] = str(uuid.uuid1())
    if change == 'date': generation['interval']['started_at'] = '2026-02-30T00:00:00.000000Z'
    if change == 'clock': generation['interval']['wall_end_before_start'] = True
    if change == 'elapsed': generation['interval']['elapsed_ms'] = -1
    if change == 'missing': del generation['sources']
    if change == 'extra': generation['trusted'] = True
    if change == 'payload': document['observation'] = 'unexpected edit'
    if change == 'binding': generation['binding_sha256'] = '0' * 64
    if change == 'component': generation['sources']['files']['component_report_sha256'] = '0' * 64
    if change == 'control': generation['sources']['journal']['control']['generation'] += 1
    if change == 'legacy_claim': document['schema_version'] = 'cospace.test-delivery-audit/0.1'
    if change == 'missing_generation': del document['generation']
    with pytest.raises(DeliveryReportError, match='delivery_report_unavailable'):
        read(document)


def test_backward_wall_clock_preserves_monotonic_duration(contextual):
    document, read = contextual
    interval = document['generation']['interval']
    interval.update(started_at='2026-10-27T00:00:02.000000Z', finished_at='2026-10-27T00:00:01.000000Z',
                    wall_end_before_start=True, elapsed_ms=100)
    result = read(document)
    assert result['report']['generation']['interval'] == interval
    assert result['report']['validity'] == 'not_evaluated'


def test_checked_in_metadata_schema_matches_runtime_contract(contextual):
    document, _ = contextual
    schema = json.loads(Path('contracts/schemas/delivery-generation-v0.1.schema.json').read_text(encoding='utf-8'))
    assert schema == ReportGeneration.model_json_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(document['generation'])
    invalid = copy.deepcopy(document['generation'])
    del invalid['report_id']
    assert list(validator.iter_errors(invalid))


def test_source_locator_is_not_store_or_content_identity(contextual, tmp_path):
    document, _ = contextual
    report = {k: v for k, v in document.items() if k != 'generation'}
    first = generation_context(report, tmp_path / 'files', tmp_path / 'journal', 100)
    moved = generation_context(report, tmp_path / 'moved-files', tmp_path / 'journal', 100)
    assert first['sources']['files']['locator_sha256'] != moved['sources']['files']['locator_sha256']
    assert first['sources']['files']['component_report_sha256'] == moved['sources']['files']['component_report_sha256']
    report['components']['files']['extra_diagnostic'] = 'changed'
    changed = generation_context(report, tmp_path / 'files', tmp_path / 'journal', 100)
    assert first['sources']['files']['locator_sha256'] == changed['sources']['files']['locator_sha256']
    assert first['sources']['files']['component_report_sha256'] != changed['sources']['files']['component_report_sha256']
