import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from packages.data.preview_inputs import PreviewInputs
from packages.construction.preview_jobs import PreviewJobs
from packages.construction.preview_model import digest
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_real_model_preview import make_preview


def source(tmp_path):
    snapshot=tmp_path/'snapshot'; raw=snapshot/'raw'; raw.mkdir(parents=True)
    (raw/'d.pgm').write_bytes(b'P5\n640 480\n65535\n'+b'\0\1'*(640*480))
    (raw/'r.ppm').write_bytes(b'P6\n640 480\n255\n'+b'\x80'*(640*480*3))
    report={'schema_version':'cospace.nyu-short-scene/0.1',
            'pairs':[{'accepted':True,'depth':'d.pgm','rgb':'r.ppm'}],
            'members':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in raw.iterdir()}}
    (snapshot/'report.json').write_text(json.dumps(report),encoding='utf-8')
    tracking=tmp_path/'tracking.json'
    tracking.write_text(json.dumps({'source_report_sha256':digest(snapshot/'report.json'),
                                   'prefix_T_anchor_camera':[np.eye(4).tolist()]}),encoding='utf-8')
    return snapshot,tracking


def test_registration_persists_and_rechecks_changes(tmp_path):
    snapshot,tracking=source(tmp_path); catalog=PreviewInputs(tmp_path/'catalog')
    record=catalog.register('办公室',snapshot,tracking)
    assert record['verified_image_members']==2 and record['used_frames']==1
    assert 'snapshot' not in catalog.list()[0] and 'tracking' not in catalog.list()[0]
    assert PreviewInputs(catalog.root).resolve(record['id'])==record
    (snapshot/'raw'/'d.pgm').write_bytes(b'changed')
    with pytest.raises(ValueError,match='input_integrity'): catalog.resolve(record['id'])
    with pytest.raises(ValueError,match='input_not_found'): catalog.resolve('../outside')


def test_wrong_tracking_and_bad_format_refused(tmp_path):
    snapshot,tracking=source(tmp_path); catalog=PreviewInputs(tmp_path/'catalog')
    poses=json.loads(tracking.read_bytes()); poses['source_report_sha256']='wrong'
    tracking.write_text(json.dumps(poses),encoding='utf-8')
    with pytest.raises(ValueError,match='source_mismatch'): catalog.register('bad',snapshot,tracking)
    report=json.loads((snapshot/'report.json').read_bytes()); report['schema_version']='pcd'
    (snapshot/'report.json').write_text(json.dumps(report),encoding='utf-8')
    with pytest.raises(ValueError,match='unsupported_input_format'): catalog.register('bad',snapshot,tracking)
    assert catalog.list()==[]


def test_explicit_input_required_and_subprocess_binding(tmp_path,monkeypatch):
    snapshot,tracking=source(tmp_path); catalog=PreviewInputs(tmp_path/'catalog')
    one=catalog.register('one',snapshot,tracking); two=catalog.register('two',snapshot,tracking)
    jobs=PreviewJobs(tmp_path/'jobs',tmp_path/'unused',tmp_path/'unused.json',catalog)
    initial=tmp_path/'initial'; initial.mkdir(); make_preview(initial)
    command=[]
    class Process:
        def poll(self): return 1
    def launch(args,**kwargs): command.extend(args); return Process()
    monkeypatch.setattr('packages.construction.preview_jobs.subprocess.Popen',launch)
    with TestClient(create_app(initial,jobs)) as client:
        assert len(client.get('/api/inputs').json()['inputs'])==2
        assert client.post('/api/builds').status_code==409
        assert client.post('/api/builds',json={'input_id':'missing'}).status_code==409
        assert client.post('/api/builds',json={'input_id':one['id']},headers={'Origin':'https://example.com'}).status_code==403
        response=client.post('/api/builds',json={'input_id':two['id']})
        assert response.status_code==202
        record=response.json()
        assert record['input_id']==two['id'] and record['input_binding']['label']=='two'
        assert command[command.index('--snapshot')+1]==str(snapshot.resolve())
        assert '--input-binding' in command
        jobs.list()  # Reap mocked failed process, close its log.
    tracking.write_bytes(b'changed')
    with pytest.raises(ValueError): jobs.start(one['id'])
    assert len(jobs.list())==1


def test_unsafe_member_name_refused(tmp_path):
    snapshot,tracking=source(tmp_path); report=json.loads((snapshot/'report.json').read_bytes())
    report['pairs'][0]['depth']='../outside.pgm'
    (snapshot/'report.json').write_text(json.dumps(report),encoding='utf-8')
    poses=json.loads(tracking.read_bytes()); poses['source_report_sha256']=digest(snapshot/'report.json')
    tracking.write_text(json.dumps(poses),encoding='utf-8')
    with pytest.raises(ValueError,match='invalid_input_member'):
        PreviewInputs(tmp_path/'catalog').register('bad',snapshot,tracking)
