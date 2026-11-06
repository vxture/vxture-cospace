import json
import pytest
from fastapi.testclient import TestClient
from test_preview_inputs import source
from test_real_model_preview import make_preview
from packages.data.preview_source_config import load_sources
from packages.data.preview_inputs import PreviewInputs
from packages.construction.preview_jobs import PreviewJobs
from experiments.scripts.serve_nyu_flow_preview import create_app


def configuration(tmp_path):
    source(tmp_path)
    data={'profile':'cospace.preview-sources/0.1','sources':[{
        'id':'office','label':'office','enabled':True,'format':'nyu_rgbd_with_existing_poses',
        'snapshot':'snapshot','tracking':'tracking.json'}]}
    path=tmp_path/'sources.json'
    path.write_text(json.dumps(data),encoding='utf-8')
    return path,data


def test_load_full_check_disabled_and_status(tmp_path):
    path,data=configuration(tmp_path)
    data['sources'].append({**data['sources'][0],'id':'future','enabled':False,'snapshot':'not-yet-present'})
    path.write_text(json.dumps(data),encoding='utf-8')
    allowed,report=load_sources(path,tmp_path,True)
    assert list(allowed)==['office'] and report['enabled_count']==1 and report['disabled_count']==1
    assert [s['status'] for s in report['sources']]==['validated','disabled']
    assert 'snapshot' not in json.dumps(report)
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path,tmp_path,PreviewInputs(tmp_path/'catalog'))
    initial=tmp_path/'initial'; initial.mkdir(); make_preview(initial)
    with TestClient(create_app(initial,jobs,registration_sources=allowed,source_config_status=report)) as client:
        response=client.get('/api/registration-sources').json()
        assert response['configuration']['sha256']==report['sha256']
        assert client.post('/api/inputs',json={'source_id':'future','label':'future'}).status_code==409
        assert jobs.inputs.list()==[]


@pytest.mark.parametrize('change',[
    {'snapshot':'../outside'}, {'snapshot':'D:/outside'}, {'tracking':'/outside'},
    {'format':'unknown'}, {'enabled':'false'}, {'unexpected':True}, {'label':' '}, {'id':'../bad'}])
def test_invalid_configuration_refused(tmp_path,change):
    path,data=configuration(tmp_path); data['sources'][0].update(change)
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError): load_sources(path,tmp_path)


def test_duplicate_profile_missing_and_snapshot_check(tmp_path):
    path,data=configuration(tmp_path)
    data['sources'].append(data['sources'][0])
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='duplicate'): load_sources(path,tmp_path)
    data['sources'].pop(); data['profile']='unknown'
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='unsupported'): load_sources(path,tmp_path)
    data['profile']='cospace.preview-sources/0.1'
    path.write_text(json.dumps(data),encoding='utf-8')
    _,basic=load_sources(path,tmp_path)
    assert basic['full_file_check'] is False and basic['sources'][0]['status']=='configured'
    (tmp_path/'snapshot'/'raw'/'d.pgm').write_bytes(b'changed')
    with pytest.raises(ValueError,match='input_integrity'): load_sources(path,tmp_path,True)
    (tmp_path/'tracking.json').unlink()
    with pytest.raises(ValueError,match='missing_files'): load_sources(path,tmp_path)


def test_config_change_requires_new_load_and_empty_disables_all(tmp_path):
    path,data=configuration(tmp_path); allowed,report=load_sources(path,tmp_path)
    data['sources']=[]; path.write_text(json.dumps(data),encoding='utf-8')
    assert list(allowed)==['office']
    new,new_report=load_sources(path,tmp_path)
    assert new=={} and new_report['sha256']!=report['sha256']
