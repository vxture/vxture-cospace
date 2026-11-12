from urllib.parse import urlparse, parse_qs
from fastapi.testclient import TestClient
from experiments.scripts.serve_nyu_flow_preview import create_app
from packages.views.viewer_entry import viewer_href, write_viewer_entry
from test_preview_workflow import prepared


def test_old_viewer_routes_redirect_to_exact_record_without_mutating_fixed_files(tmp_path):
    initial, jobs, directory, spaces, ontologies, _, old, current = prepared(tmp_path)
    from packages.service.preview_publications import PreviewPublications
    publications = PreviewPublications(jobs)
    frozen = publications.root/current['id']
    before = {p.name: p.read_bytes() for p in frozen.iterdir() if p.is_file()}
    with TestClient(create_app(initial, jobs, space_directory=directory, ontologies=ontologies)) as client:
        for group, identity, field in [('candidates', current['candidate_id'], 'job'),
                                       ('publications', current['id'], 'publication')]:
            for suffix in ('/', '/index.html'):
                response = client.get(f'/{group}/{identity}{suffix}', follow_redirects=False)
                assert response.status_code == 307
                url = urlparse(response.headers['location'])
                assert url.path == '/space'
                assert parse_qs(url.query) == {'screen': ['space'], 'preview': ['1'],
                                              'space': [spaces[0]['id']], field: [identity]}
            metadata=client.get(f'/{group}/{identity}/api/preview')
            assert metadata.status_code == 200
            assert 'model.json' in metadata.json()['inspection_files']
            for name in metadata.json()['inspection_files']:
                assert client.get(f'/{group}/{identity}/{name}').status_code == 200
        assert client.get('/candidates/missing/', follow_redirects=False).status_code == 404
        assert client.get('/publications/missing/index.html', follow_redirects=False).status_code == 404
    assert {p.name: p.read_bytes() for p in frozen.iterdir() if p.is_file()} == before


def test_new_artifact_entry_is_only_an_escaped_link_not_a_second_renderer(tmp_path):
    write_viewer_entry(tmp_path, {'space_id': 'space-one', 'id': 'build-one'})
    text = (tmp_path/'index.html').read_text(encoding='utf-8')
    assert 'http-equiv="refresh"' in text and '<canvas' not in text and '<script' not in text
    assert 'job=build-one' in text and '&amp;space=space-one' in text
    assert 'publication=' in viewer_href('space-one', publication_id='pub-one')
