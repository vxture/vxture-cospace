import io
import json
import socket
import zipfile
import pytest
from fastapi.testclient import TestClient
from test_preview_publications import fixture
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.preview_offline import OfflinePreview, export_bundle, sha, bounded_zip
from experiments.scripts.serve_nyu_flow_preview import create_app


def setup_bundle(tmp_path):
    initial,jobs=fixture(tmp_path)
    jobs.select('build-one',0)
    publications=PreviewPublications(jobs)
    record=publications.publish('build-one',1)
    _,model=publications.read(record['id'])
    return initial,jobs,record,export_bundle(record,model)


def test_http_download_matches_offline_without_network(tmp_path,monkeypatch):
    initial,jobs,record,bundle=setup_bundle(tmp_path)
    with TestClient(create_app(initial,jobs)) as client:
        url=record['preview_url']
        response=client.get(url+'offline.zip')
        assert response.status_code==200 and response.content==bundle
        assert response.headers['x-cospace-package-sha256']==sha(bundle)
        info=client.get(url+'offline.json').json()
        assert info['sha256']==sha(bundle) and info['bytes']==len(bundle)
        points=[[-.05,.05,.05],[0,0,0],[100,100,100]]
        online=[client.post(url+'api/query',json={'point_m':p}).json() for p in points]
    def no_network(*args,**kwargs): raise AssertionError('network must not be used')
    monkeypatch.setattr(socket,'socket',no_network)
    offline=OfflinePreview(bundle,record['id'],sha(bundle))
    assert [offline.query(p) for p in points]==online
    assert online[1]['state']=='unknown' and online[1]['robot_ready'] is False
    with pytest.raises(ValueError,match='invalid_point'): offline.query([float('nan'),0,0])
    assert set(zipfile.ZipFile(io.BytesIO(bundle)).namelist())=={
        'package.json','publication.json','model.json','agent.npz'}


def test_wrong_delivery_and_changed_bytes_refused(tmp_path):
    _,_,record,bundle=setup_bundle(tmp_path)
    with pytest.raises(ValueError,match='package_binding'):
        OfflinePreview(bundle,'preview-wrong',sha(bundle))
    with pytest.raises(ValueError,match='package_integrity'):
        OfflinePreview(bundle+b'changed',record['id'],sha(bundle))
    files=bounded_zip(bundle,{'package.json','publication.json','model.json','agent.npz'},32*1024*1024)
    files['agent.npz']=b'changed'
    with pytest.raises(ValueError,match='member_integrity'):
        changed=pack(files)
        OfflinePreview(changed,record['id'],sha(changed))


def pack(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in files.items(): archive.writestr(name,data)
    return stream.getvalue()


def test_unsafe_duplicate_and_oversized_members_refused():
    for members in [{'../cells.npy':b'x'},{'cells.npy':b'12345'}]:
        with pytest.raises(ValueError,match='invalid_archive'):
            bounded_zip(pack(members),{'cells.npy'},4)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        archive.writestr('cells.npy',b'a')
        with pytest.warns(UserWarning): archive.writestr('cells.npy',b'b')
    with pytest.raises(ValueError,match='invalid_archive'):
        bounded_zip(stream.getvalue(),{'cells.npy'},100)


def test_self_consistent_package_cannot_change_publication_binding(tmp_path):
    _,_,record,bundle=setup_bundle(tmp_path)
    files=bounded_zip(bundle,{'package.json','publication.json','model.json','agent.npz'},32*1024*1024)
    model=json.loads(files['model.json']); model['frame_id']='different'
    files['model.json']=json.dumps(model).encode()
    package=json.loads(files['package.json'])
    package['files']['model.json']={'sha256':sha(files['model.json']),'bytes':len(files['model.json'])}
    files['package.json']=json.dumps(package).encode()
    changed=pack(files)
    with pytest.raises(ValueError,match='publication_binding'):
        OfflinePreview(changed,record['id'],sha(changed))
