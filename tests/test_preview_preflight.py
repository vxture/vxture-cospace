import json
from fastapi.testclient import TestClient
from test_preview_inputs import source
from test_real_model_preview import make_preview
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_preflight import preflight
from packages.construction.preview_jobs import PreviewJobs
from experiments.scripts.serve_nyu_flow_preview import create_app


def setup(tmp_path):
    snapshot,tracking=source(tmp_path)
    catalog=PreviewInputs(tmp_path/'catalog'); record=catalog.register('office',snapshot,tracking)
    jobs=PreviewJobs(tmp_path/'jobs',snapshot,tracking,catalog)
    initial=tmp_path/'initial'; initial.mkdir(); make_preview(initial)
    return snapshot,tracking,catalog,record,jobs,initial


def test_detail_and_preflight_are_read_only_and_not_build_authority(tmp_path):
    snapshot,_,catalog,record,jobs,initial=setup(tmp_path)
    before=(catalog.root/(record['id']+'.json')).read_bytes()
    with TestClient(create_app(initial,jobs)) as client:
        base='/api/inputs/'+record['id']
        detail=client.get(base).json()
        assert detail['snapshot']==str(snapshot.resolve())
        assert len(detail['limitations'])==3
        assert client.post(base+'/preflight',headers={'Origin':'https://example.com'}).status_code==403
        report=client.post(base+'/preflight').json()
        assert report['status']=='passed' and report['robot_ready'] is False
        assert report['input_id']==record['id'] and report['counts_basis']=='registration'
        (snapshot/'raw'/'d.pgm').write_bytes(b'changed')
        failed=client.post(base+'/preflight').json()
        assert failed['status']=='failed' and failed['issue']['code']=='input_integrity'
        assert failed['issue']['action']
        # Earlier successful preview does not authorize building changed input.
        assert client.post('/api/builds',json={'input_id':record['id']}).status_code==409
        assert client.get('/api/inputs/input-missing').status_code==404
        assert client.post('/api/inputs/input-missing/preflight').status_code==404
    assert jobs.list()==[] and jobs.selection()['revision']==0
    assert (catalog.root/(record['id']+'.json')).read_bytes()==before


def test_missing_file_has_actionable_reason(tmp_path):
    _,tracking,catalog,record,_,_=setup(tmp_path)
    tracking.unlink()
    report=preflight(catalog,record['id'])
    assert report['status']=='failed' and report['issue']['code']=='input_file_missing'
    assert '恢复' in report['issue']['action']


def test_malformed_file_has_no_raw_path_or_exception_leak(tmp_path):
    _,tracking,catalog,record,_,_=setup(tmp_path)
    tracking.write_bytes(b'not json')
    report=preflight(catalog,record['id'])
    assert report['issue']['code']=='invalid_input_content'
    assert str(tracking) not in json.dumps(report)
