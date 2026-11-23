"""Fixture text must remain data even when it contains executable markup."""
import json

from fastapi.testclient import TestClient
import pytest

from experiments.scripts.model_loading_lab import create_app, SAMPLES


@pytest.fixture
def lab(tmp_path):
    root, assets = tmp_path / 'lab', tmp_path / 'assets'
    root.mkdir()
    assets.mkdir()
    malicious = '</div><script>alert(1)</script>" onmouseover="alert(2) & text'
    (root / 'fixtures.json').write_text(json.dumps({SAMPLES[0]: {'display': {'label': malicious}}}))
    return TestClient(create_app(root, assets)), malicious


def test_fixture_markup_roundtrips_as_data_without_creating_executable_markup(lab):
    client, malicious = lab
    response = client.get('/loading-lab?task=true&strategy=baseline')
    assert response.status_code == 200 and malicious not in response.text
    assert '<script>alert(1)</script>' not in response.text
    data = client.get('/loading-lab/fixture?task=true&strategy=baseline')
    assert data.headers['content-type'] == 'application/json'
    assert data.headers['x-content-type-options'] == 'nosniff'
    assert data.headers['cache-control'] == 'no-store'
    assert data.json()['display']['label'] == malicious
    assert data.json()['task'] is True and data.json()['strategy'] == 'baseline'


@pytest.mark.parametrize('query', ['sample=other', 'strategy=unreviewed', 'sample=%3Cscript%3E'])
@pytest.mark.parametrize('path', ['/loading-lab', '/loading-lab/fixture'])
def test_lab_does_not_reflect_unrecognized_samples_or_policies(lab, query, path):
    client, _ = lab
    response = client.get(path + '?' + query)
    assert response.status_code == 422 and response.headers['content-type'].startswith('application/json')
