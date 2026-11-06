from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from test_preview_inputs import source
from test_real_model_preview import make_preview
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_registration import PreviewRegistration
from packages.construction.preview_jobs import PreviewJobs
from experiments.scripts.serve_nyu_flow_preview import create_app


def setup(tmp_path):
    snapshot,tracking=source(tmp_path)
    catalog=PreviewInputs(tmp_path/'catalog')
    jobs=PreviewJobs(tmp_path/'jobs',snapshot,tracking,catalog)
    initial=tmp_path/'initial'; initial.mkdir(); make_preview(initial)
    sources={'office':{'label':'office','snapshot':snapshot,'tracking':tracking}}
    return initial,jobs,sources


def test_allowed_registration_duplicate_and_no_business_side_effects(tmp_path):
    initial,jobs,sources=setup(tmp_path)
    with TestClient(create_app(initial,jobs,registration_sources=sources)) as client:
        options=client.get('/api/registration-sources').json()['sources']
        assert options==[{'id':'office','label':'office','format':'nyu_rgbd_with_existing_poses'}]
        body={'source_id':'office','label':'my office'}
        first=client.post('/api/inputs',json=body)
        assert first.status_code==201 and first.json()['created'] is True
        assert 'snapshot' not in first.json()['input']
        second=client.post('/api/inputs',json={**body,'label':'another name'})
        assert second.status_code==200 and second.json()['created'] is False
        assert second.json()['input']['id']==first.json()['input']['id']
        assert second.json()['input']['label']=='my office'
        assert len(jobs.inputs.list())==1 and jobs.list()==[] and jobs.selection()['revision']==0


def test_unknown_extra_paths_origin_and_invalid_source_refused(tmp_path):
    initial,jobs,sources=setup(tmp_path)
    with TestClient(create_app(initial,jobs,registration_sources=sources)) as client:
        body={'source_id':'office','label':'office'}
        assert client.post('/api/inputs',json=body,headers={'Origin':'https://example.com'}).status_code==403
        assert client.post('/api/inputs',json={**body,'snapshot':'C:/outside'}).status_code==422
        assert client.post('/api/inputs',json={**body,'source_id':'../outside'}).status_code==409
        assert client.post('/api/inputs',json={**body,'label':'   '}).status_code==409
        (sources['office']['snapshot']/'raw'/'d.pgm').write_bytes(b'changed')
        failed=client.post('/api/inputs',json=body)
        assert failed.status_code==409 and failed.json()['detail']=='registration_validation_failed'
        assert jobs.inputs.list()==[]


def test_concurrent_duplicate_registers_once(tmp_path):
    _,jobs,sources=setup(tmp_path)
    registration=PreviewRegistration(jobs.inputs,sources)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:registration.register('office','office'),range(2)))
    assert sorted(r['created'] for r in results)==[False,True]
    assert len(jobs.inputs.list())==1


def test_unconfigured_sources_do_not_allow_registration(tmp_path):
    initial,jobs,_=setup(tmp_path)
    with TestClient(create_app(initial,jobs)) as client:
        assert client.get('/api/registration-sources').json()=={'sources':[]}
        assert client.post('/api/inputs',json={'source_id':'office','label':'office'}).status_code==409
