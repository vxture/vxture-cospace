"""Saved diagnostic API: no paths from clients, no scans, no permission promotion."""
import copy
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from apps.api.managed import create_managed_app
from packages.service.delivery import DeliveryReportError, SavedDeliveryReader


@pytest.fixture
def saved(tmp_path):
    source = Path('tests/fixtures/p2-delivery-audit-001/scenario.json')
    scenarios = json.loads(source.read_text(encoding='utf-8'))['scenarios']
    target = tmp_path / 'report.json'
    target.write_text(json.dumps(scenarios['clean']), encoding='utf-8')
    binding = scenarios['clean']['requested_binding']
    url = f"/scenes/{binding['scene_id']}/releases/{binding['release_id']}/delivery"
    return target, scenarios, url


@pytest.mark.parametrize('scenario', ['clean', 'pending', 'planned', 'reconciled_missing_grant'])
def test_saved_reports_are_projected_readonly(saved, scenario):
    target, scenarios, url = saved
    value = copy.deepcopy(scenarios[scenario])
    value['components']['journal']['unexpected_private_material'] = 'must-not-leave-reader'
    target.write_text(json.dumps(value), encoding='utf-8')
    before = target.read_bytes()
    with TestClient(create_managed_app(None, delivery_reader=SavedDeliveryReader(target))) as client:
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        body = response.json()
        assert body['source']['sha256'] == hashlib.sha256(before).hexdigest()
        assert body['source']['observed_at'] is None
        assert body['report']['findings'] == value['findings']
        assert body['report']['authorized'] is False
        assert body['report']['validity'] == 'not_evaluated'
        assert 'must-not-leave-reader' not in response.text and str(target) not in response.text
    assert target.read_bytes() == before
    assert list(target.parent.iterdir()) == [target]


def test_refresh_reads_replaced_report_then_fails_without_old_body(saved):
    target, scenarios, url = saved
    with TestClient(create_managed_app(None, delivery_reader=SavedDeliveryReader(target))) as client:
        clean = client.get(url).json()
        target.write_text(json.dumps(scenarios['pending']), encoding='utf-8')
        pending = client.get(url).json()
        assert clean['source']['sha256'] != pending['source']['sha256']
        assert pending['report']['needs_attention']
        target.write_text('broken', encoding='utf-8')
        bad = client.get(url)
        assert bad.status_code == 503 and 'report' not in bad.json()
        assert bad.headers['cache-control'] == 'no-store'


def test_unconfigured_and_missing_do_not_create_stores(saved):
    target, _, url = saved
    target.unlink()
    for reader in [None, SavedDeliveryReader(target)]:
        with TestClient(create_managed_app(None, delivery_reader=reader)) as client:
            response = client.get(url)
            assert response.status_code == 503
            assert response.headers['cache-control'] == 'no-store'
    assert not target.exists()


def test_wrong_target_and_write_methods_rejected(saved):
    target, _, url = saved
    with TestClient(create_managed_app(None, delivery_reader=SavedDeliveryReader(target))) as client:
        assert client.get(url.replace('synthetic-equipment-corridor', 'different-scene')).status_code == 409
        assert client.get(url.replace('release-spatial-sample-001', 'different-release')).status_code == 409
        for method in ['post', 'put', 'delete']:
            assert getattr(client, method)(url).status_code == 405


@pytest.mark.parametrize('change', ['authorization', 'binding', 'findings', 'schema', 'type'])
def test_invalid_diagnostic_boundaries_rejected(saved, change):
    target, scenarios, _ = saved
    value = copy.deepcopy(scenarios['clean'])
    if change == 'authorization': value['authorized'] = True
    if change == 'binding': value['observed']['binding_match'] = False
    if change == 'findings': value['needs_attention'] = True
    if change == 'schema': value['schema_version'] = 'production'
    if change == 'type': value['complete'] = 'true'
    target.write_text(json.dumps(value), encoding='utf-8')
    binding = scenarios['clean']['requested_binding']
    with pytest.raises(DeliveryReportError, match='delivery_report_unavailable'):
        SavedDeliveryReader(target).read(binding['scene_id'], binding['release_id'])


def test_oversize_report_rejected(saved):
    target, scenarios, _ = saved
    target.write_bytes(b' ' * (SavedDeliveryReader.MAX_BYTES + 1))
    binding = scenarios['clean']['requested_binding']
    with pytest.raises(DeliveryReportError, match='delivery_report_unavailable'):
        SavedDeliveryReader(target).read(binding['scene_id'], binding['release_id'])
