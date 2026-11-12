"""HTTP error responses retain business codes without exposing diagnostics."""
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest
from experiments.scripts.platform_auth_fixture import MockAccounts
from experiments.scripts.serve_nyu_flow_preview import create_app
from fastapi.testclient import TestClient
from packages.data.input_preview import PreviewUnavailable
from packages.data.input_uploads import UploadRejected
from packages.data.input_coordinates import CoordinatesConflict
from packages.data.input_facts import FactsUnavailable
from packages.data.space_sources import SourcesConflict
from packages.lifecycle.workspace_scenes import WorkspaceScenesConflict
from packages.service.public_errors import public_error
from packages.service.preview_publications import PreviewPublications
from packages.ontology.workspace_authoring import WorkspaceOntologies
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_online_consumer import consumer


DIAGNOSTIC='internal-diagnostic-marker /private/runtime/file.json'


@pytest.mark.parametrize('exception',[ValueError,TypeError,KeyError,OSError])
def test_public_error_only_returns_an_allowed_constant(exception):
    assert public_error(exception(DIAGNOSTIC),('known_conflict',),'unavailable')=='unavailable'
    assert public_error(exception('known_conflict'),('known_conflict',),'unavailable')==(
        'unavailable' if exception is KeyError else 'known_conflict')
    assert public_error(exception('known_conflict\n'+DIAGNOSTIC),('known_conflict',),'unavailable')=='unavailable'


@pytest.mark.parametrize('exception,code,status',[
    (PreviewUnavailable,'preview_unavailable',409),
    (UploadRejected,'upload_package_invalid',422),
    (CoordinatesConflict,'input_coordinates_unavailable',409),
    (FactsUnavailable,'input_evidence_invalid',409),
    (SourcesConflict,'source_settings_unavailable',409),
    (WorkspaceScenesConflict,'workspace_scene_creation_unavailable',409),
])
def test_business_custom_exceptions_do_not_leak(secured,monkeypatch,exception,code,status):
    _,client,_,_,jobs,_,spaces,*_=secured
    sign_in(secured,'usr_engineer')
    identity=json.loads((jobs.root/'build-one/job.json').read_bytes())['input_id']
    def fail(*args,**kwargs):raise exception(DIAGNOSTIC)
    monkeypatch.setattr('packages.service.platform_business_http.input_preview',fail)
    response=client.get(f'/api/inputs/{identity}/preview',params={'space_id':spaces[0]['id']})
    assert response.status_code==status,response.text
    assert response.json()=={'detail':code}
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('message,expected',[(DIAGNOSTIC,'preview_unavailable'),
    ('input_preview_evidence_unavailable','input_preview_evidence_unavailable')])
def test_business_preview_keeps_known_codes(secured,monkeypatch,message,expected):
    _,client,_,_,jobs,_,spaces,*_=secured
    sign_in(secured,'usr_engineer')
    identity=json.loads((jobs.root/'build-one/job.json').read_bytes())['input_id']
    def fail(*args,**kwargs):raise PreviewUnavailable(message)
    monkeypatch.setattr('packages.service.platform_business_http.input_preview',fail)
    response=client.get(f'/api/inputs/{identity}/preview',params={'space_id':spaces[0]['id']})
    assert response.status_code==409 and response.json()=={'detail':expected}


@pytest.mark.parametrize('message,expected',[(DIAGNOSTIC,'ontology_authoring_failed'),
    ('ontology_draft_integrity','ontology_draft_integrity')])
def test_ontology_broad_exception_vocabulary(secured,monkeypatch,message,expected):
    _,client,accounts,*_=secured
    accounts.roles=['workspace:owner'];sign_in(secured,'usr_owner')
    def fail(*args,**kwargs):raise ValueError(message)
    monkeypatch.setattr(WorkspaceOntologies,'drafts',fail)
    response=client.get('/api/ontology-authoring')
    assert response.status_code==409 and response.json()=={'detail':expected},response.text


@pytest.mark.parametrize('message,expected',[(DIAGNOSTIC,'lifecycle_transition_unavailable'),
    ('lifecycle_changed_refresh_required','lifecycle_changed_refresh_required')])
def test_lifecycle_broad_exception_vocabulary(secured,monkeypatch,message,expected):
    from test_publication_retirement import request as retirement
    from packages.lifecycle.preview_control import PreviewControls
    _,client,_,_,jobs,_,spaces,_,old,new=secured
    headers,_=sign_in(secured,'usr_manager')
    command=retirement(jobs,PreviewPublications(jobs),spaces[0]['id'],old,new)
    def fail(*args,**kwargs):raise ValueError(message)
    monkeypatch.setattr(PreviewControls,'change',fail)
    response=client.post('/api/artifact-control/transitions',json=command.model_dump(),headers=headers)
    assert response.status_code==409 and response.json()=={'detail':expected},response.text


@pytest.mark.parametrize('message,code,status',[(DIAGNOSTIC,'consumer_request_or_publication_invalid',422),
    ('consumer_frame_mismatch','consumer_frame_mismatch',409)])
def test_consumer_exception_vocabulary(consumer,monkeypatch,message,code,status):
    client,route,body,headers,_,_,access,*_=consumer
    def fail(*args,**kwargs):raise ValueError(message)
    monkeypatch.setattr(access.consumer,'query',fail)
    response=client.post(route,json=body,headers=headers)
    assert response.status_code==status and response.json()=={'detail':code}
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('message,code,status',[(DIAGNOSTIC,'publication_distribution_unavailable',409),
    ('publication_not_found','publication_not_found',404),
    ('publication_distribution_paused','publication_distribution_paused',409)])
def test_distribution_exception_vocabulary(secured,monkeypatch,message,code,status):
    _,_,_,_,jobs,directory,_,_,_,new=secured
    def fail(*args,**kwargs):raise ValueError(message)
    monkeypatch.setattr(PreviewPublications,'require_distributing',fail)
    with TestClient(create_app(None,jobs,space_directory=directory,platform_origin='http://127.0.0.1')) as client:
        response=client.get(f'/publications/{new["id"]}/model.json')
    assert response.status_code==status and response.json()=={'detail':code}
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('control',['\r\nX-Injected: yes','\r','\n','\x00','\x7f'])
def test_local_idp_rejects_header_control_characters(control):
    from urllib.error import HTTPError
    accounts=MockAccounts().start()
    try:
        accounts.rp_origin='http://127.0.0.1/rp'+control
        query=urlencode({'client_id':accounts.client_id,
                         'post_logout_redirect_uri':accounts.rp_origin+'/'})
        with pytest.raises(HTTPError) as caught:urlopen(accounts.issuer+'/oidc/end_session?'+query)
        assert caught.value.code==400
        assert caught.value.headers.get('X-Injected') is None
        assert json.loads(caught.value.read())=={'error':'invalid_redirect'}
    finally:accounts.stop()


def test_frontend_encodes_untrusted_path_segments():
    # React escapes text/attributes; path segments must also be URL encoded.
    source=Path('apps/workbench/src/layout/object-annotations.tsx').read_text(encoding='utf-8')
    assert 'href={candidateScreenHref(target.space,baseId)}' in source
    source=Path('apps/workbench/src/layout/real-space-data.ts').read_text(encoding='utf-8')
    assert "new URLSearchParams({screen:'space',preview:'1',space,job})" in source
    source=Path('apps/workbench/src/layout/real-space.tsx').read_text(encoding='utf-8')
    assert 'encodeURIComponent(candidate?current.job:current.publication)' in source
