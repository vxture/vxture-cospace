"""No-replace publication and explicit digest-bound selection over bounded local reports."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import uuid

from fastapi.testclient import TestClient
import pytest

from apps.api.managed import create_managed_app
from packages.infrastructure.delivery_reports import publish, ReportArchive, separate_output
from packages.service.delivery import DeliveryReportError


@pytest.fixture
def reports():
    return json.loads(Path('tests/fixtures/p2-delivery-context-001/scenario.json').read_text(encoding='utf-8'))['scenarios']


def test_publish_read_and_explicit_list(tmp_path, reports):
    first = publish(tmp_path, reports['clean'])
    second = publish(tmp_path, reports['pending'])
    binding = reports['clean']['requested_binding']
    archive = ReportArchive(tmp_path)
    target = (binding['scene_id'], binding['release_id'])
    listing = archive.list(*target)
    assert len(listing['items']) == 2 and listing['selection'] == 'explicit_key_required'
    assert [i['report_key'] for i in listing['items']] == sorted([first['report_key'], second['report_key']])
    assert not archive.read(*target, first['report_key'])['report']['needs_attention']
    assert archive.read(*target, second['report_key'])['report']['needs_attention']
    assert not list(tmp_path.glob('.writing-*'))


def test_competing_publication_has_single_winner(tmp_path, reports):
    def attempt():
        try: return publish(tmp_path, reports['clean'])
        except FileExistsError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(r is not None for r in results) == 1
    assert len(list(tmp_path.glob('*.json'))) == 1 and not list(tmp_path.glob('.writing-*'))


def test_link_failure_never_exposes_partial_report(tmp_path, reports, monkeypatch):
    import packages.infrastructure.delivery_reports as module
    def fail(source, destination):
        assert Path(source).read_bytes().endswith(b'}')
        assert not Path(destination).exists()
        raise OSError('injected publish failure')
    monkeypatch.setattr(module.os, 'link', fail)
    with pytest.raises(OSError): publish(tmp_path, reports['clean'])
    assert not list(tmp_path.iterdir())


def test_killed_writer_leaves_only_ignored_staging(tmp_path, reports):
    source = tmp_path / 'source.txt'
    source.write_text(json.dumps(reports['clean']), encoding='utf-8')
    archive = tmp_path / 'archive'
    code = ('import os,json,sys; from pathlib import Path; '
            'import packages.infrastructure.delivery_reports as m; '
            'm.os.link=lambda *args: os._exit(77); '
            'm.publish(sys.argv[1],json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))')
    child = subprocess.run([sys.executable, '-c', code, str(archive), str(source)], timeout=15)
    assert child.returncode == 77
    assert len(list(archive.glob('.writing-*'))) == 1 and not list(archive.glob('*.json'))
    binding = reports['clean']['requested_binding']
    assert ReportArchive(archive).list(binding['scene_id'], binding['release_id'])['items'] == []


@pytest.mark.parametrize('key', ['../report', 'x' * 101, str(uuid.uuid4()) + '.' + '0' * 64])
def test_invalid_or_missing_selection_never_falls_back(tmp_path, reports, key):
    publish(tmp_path, reports['clean'])
    binding = reports['clean']['requested_binding']
    with pytest.raises(DeliveryReportError):
        ReportArchive(tmp_path).read(binding['scene_id'], binding['release_id'], key)


def test_altered_bytes_rejected_and_no_partial_list(tmp_path, reports):
    receipt = publish(tmp_path, reports['clean'])
    path = tmp_path / (receipt['report_key'] + '.json')
    path.write_bytes(path.read_bytes() + b' ')
    binding = reports['clean']['requested_binding']
    with pytest.raises(DeliveryReportError): ReportArchive(tmp_path).list(binding['scene_id'], binding['release_id'])


def test_same_batch_different_content_uses_different_fixed_key(tmp_path, reports):
    first = publish(tmp_path, reports['clean'])
    value = copy.deepcopy(reports['clean'])
    value['generation']['interval']['elapsed_ms'] += 1
    second = publish(tmp_path, value)
    assert first['report_id'] == second['report_id'] and first['report_key'] != second['report_key']


def test_directory_limit_and_missing_root_do_not_create(tmp_path, reports):
    missing = tmp_path / 'missing'
    with pytest.raises(DeliveryReportError): ReportArchive(missing).list('scene', 'release')
    assert not missing.exists()
    for i in range(201): (tmp_path / str(i)).touch()
    with pytest.raises(DeliveryReportError): ReportArchive(tmp_path).list('scene', 'release')


def test_target_report_limit_returns_no_truncated_success(tmp_path, reports):
    for _ in range(51):
        value = copy.deepcopy(reports['clean'])
        value['generation']['report_id'] = str(uuid.uuid4())
        publish(tmp_path, value)
    binding = reports['clean']['requested_binding']
    with pytest.raises(DeliveryReportError): ReportArchive(tmp_path).list(binding['scene_id'], binding['release_id'])


@pytest.mark.parametrize('direction', ['inside', 'parent', 'binding'])
def test_output_cannot_overlap_observed_roots(tmp_path, direction):
    source = tmp_path / 'source'
    output = {'inside': source / 'archive', 'parent': tmp_path, 'binding': source}[direction]
    with pytest.raises(ValueError): separate_output(output, [source])
    assert not source.exists()


def test_readonly_archive_api_and_target_filter(tmp_path, reports):
    receipt = publish(tmp_path, reports['clean'])
    binding = reports['clean']['requested_binding']
    base = f"/scenes/{binding['scene_id']}/releases/{binding['release_id']}/delivery-reports"
    with TestClient(create_managed_app(None, delivery_archive=ReportArchive(tmp_path))) as client:
        listing = client.get(base)
        assert listing.status_code == 200 and listing.headers['cache-control'] == 'no-store'
        response = client.get(base + '/' + receipt['report_key'])
        assert response.status_code == 200 and response.json()['source']['report_key'] == receipt['report_key']
        assert client.get(base.replace(binding['scene_id'], 'another-scene')).json()['items'] == []
        assert client.get(base.replace(binding['scene_id'], 'another-scene') + '/' + receipt['report_key']).status_code == 409
        assert client.post(base).status_code == 405
    with TestClient(create_managed_app(None)) as client:
        assert client.get(base).status_code == 503
