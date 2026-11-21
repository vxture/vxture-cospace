from copy import deepcopy
from hashlib import sha256
import io
import json
import subprocess
import sys
import zipfile
import pytest

from packages.service.scene_registrations import SceneRegistrations
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.preview_offline import OfflinePreview, export_bundle
from test_scene_registrations_http import declared_three_dimensional_models, prepared, command
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def seed(secured, monkeypatch):
    monkeypatch.setenv('COSPACE_REGISTRATION_ADAPTERS','wgs84_local_enu/1')
    rp,client,_,_,jobs,_,_,_,_,_=secured
    headers,_=sign_in(secured,'usr_engineer')
    query,state,document=prepared(secured)
    document['target'].update(horizontal_reference='WGS84 local ENU',vertical_reference='WGS84 local ENU up')
    binding=dict(adapter='wgs84_local_enu/1',target_frame_id=document['target']['frame_id'],longitude_deg=116.4,
        latitude_deg=39.9,ellipsoidal_height_m=42.,realization='WGS84(G2139)',coordinate_epoch=2026.,evidence_ref='QA-origin')
    for action,revision,key,extra in [('save',0,1,dict(document=document,geographic_binding=binding)),('submit',1,2,{})]:
        result=client.post('/api/scene-registrations',json=command(query,state,action,revision,key,**extra),headers=headers)
        assert result.status_code==200,result.text
    headers,_=sign_in(secured,'usr_manager')
    approval=dict(evidence_note='QA only, not a field acceptance',valid_from='2020-01-01T00:00:00Z',valid_until='2099-01-01T00:00:00Z',
        bounds_m=document['source']['bounds_m'],control_evidence_verified=True,independent_checks_verified=True,datum_verified=True,extent_verified=True)
    for action,revision,key,extra in [('approve',2,3,dict(approval=approval)),('adopt',3,4,{})]:
        result=client.post('/api/scene-registrations',json=command(query,state,action,revision,key,**extra),headers=headers)
        assert result.status_code==200,result.text
    return query,state,document,headers


def test_explicit_registration_publication_and_online_offline_same_fixed_closure(secured,monkeypatch):
    query,state,document,headers=seed(secured,monkeypatch)
    _,client,_,_,jobs,directory,_,_,old,_=secured
    choice=dict(registration_revision=3,source_manifest_sha256=state['source_sha256'])
    response=client.post('/api/publication-registration-preflight',headers=headers,json=query|{'registration_selection':choice})
    assert response.status_code==200,response.text
    selection=response.json()['registration_selection']
    selected=jobs.selection(query['space_id'])
    request=query|dict(expected_revision=selected['revision'],request_id='c'*32,registration_selection=selection)
    response=client.post('/api/publications',json=request,headers=headers)
    assert response.status_code==201,response.text
    record=response.json()
    assert client.post('/api/publications',json=request,headers=headers).json()['id']==record['id']
    online=client.get(record['preview_url']+'api/registration')
    assert online.status_code==200,online.text
    assert online.json()['status']=='available'
    assert len(online.json()['objects'])==3
    _,model=PreviewPublications(jobs).read(record['id'])
    package=export_bundle(record,model)
    offline=OfflinePreview(package,record['id'],sha256(package).hexdigest())
    assert offline.registration('2026-11-21T00:00:00Z')==online.json()
    assert offline.registration('2099-01-02T00:00:00Z')['status']=='registration_outside_valid_time'
    client.post('/api/scene-registrations',json=command(query,state,'clear_adoption',4,5),headers=headers)
    assert client.get(record['preview_url']+'api/registration').json()==online.json()
    assert client.get(old['preview_url']+'api/registration').json()['status']=='registration_not_included'
    assert client.post('/api/publication-registration-preflight',headers=headers,json=query|{'registration_selection':choice}).status_code==409
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert 'registration-artifact.json' in archive.namelist()
    for suffix in ('partitions.json', 'partitions.zip'):
        response = client.get(record['preview_url'] + suffix)
        assert response.status_code == 409
        assert response.json()['detail'] == 'registration_partition_delivery_not_supported'
    path=model.root/'registration-artifact.json'
    path.write_bytes(b'corrupted')
    assert client.get(record['preview_url']+'api/registration').status_code==409


def test_registration_publication_requires_current_scene_authority(secured,monkeypatch):
    query,state,_,headers=seed(secured,monkeypatch)
    _,client,*_=secured
    headers,_=sign_in(secured,'usr_local_test')
    response=client.post('/api/publication-registration-preflight',headers=headers,json=query|{'registration_selection':dict(
        registration_revision=3,source_manifest_sha256=state['source_sha256'])})
    assert response.status_code==403


def test_registration_and_semantics_share_fixed_package_and_restore_cli(secured, monkeypatch, tmp_path):
    from test_publication_semantic_adoption import seed as semantic_seed
    from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
    semantic_query, semantic_choice = semantic_seed(secured)
    query, state, _, headers = seed(secured, monkeypatch)
    _, client, _, _, jobs, *_ = secured
    assert query == semantic_query
    semantic = client.post('/api/publication-semantic-preflight', headers=headers,
        json=query | {'semantic_selection': semantic_choice})
    registration = client.post('/api/publication-registration-preflight', headers=headers,
        json=query | {'registration_selection': dict(registration_revision=3,
                     source_manifest_sha256=state['source_sha256'])})
    assert semantic.status_code == registration.status_code == 200
    response = client.post('/api/publications', headers=headers, json=query | dict(
        expected_revision=jobs.selection(query['space_id'])['revision'], request_id='e'*32,
        semantic_selection=semantic.json()['semantic_selection'],
        registration_selection=registration.json()['registration_selection']))
    assert response.status_code == 201, response.text
    record = response.json()
    package = export_bundle(*PreviewPublications(jobs).read(record['id']))
    digest = sha256(package).hexdigest()
    path = tmp_path / 'fixed.zip'
    path.write_bytes(package)
    offline = OfflinePreview.load(path, record['id'], digest)
    assert offline.semantics()['state'] == 'included'
    assert offline.registration()['status'] == 'available'
    expected = offline.registration('2026-11-21T00:00:00Z')
    assert expected['status'] == 'available'
    root = tmp_path / 'consumer'
    store = PersistentPreviewConsumer.initialize(root, query['space_id'])
    store.install(path, record['id'], digest)
    store.activate(record['id'], digest, 0)
    restored = PersistentPreviewConsumer(root).restore(record['id'], digest, 1)
    assert restored.registration('2026-11-21T00:00:00Z') == expected | dict(
        consumer_revision=1, package_sha256=digest)
    for module, arguments in [
        ('apps.cli.preview_consumer', ['--root', str(root), 'restore', '--expected-revision', '1']),
        ('experiments.scripts.query_preview_offline', [str(path)]),
    ]:
        result = subprocess.run([sys.executable, '-m', module, *arguments,
            '--publication', record['id'], '--sha256', digest, '--registration',
            '--at', '2026-11-21T00:00:00Z'], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['objects'] == expected['objects']
