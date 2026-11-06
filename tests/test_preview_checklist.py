import json
import pytest
from fastapi.testclient import TestClient
from test_preview_offline import setup_bundle
from packages.service.preview_publications import PreviewPublications
from packages.service.preview_checklist import checklist
from packages.views.agent.preview_offline import sha
from experiments.scripts.serve_nyu_flow_preview import create_app


def test_checks_are_scoped_and_missing_records_are_not_passes(tmp_path):
    initial,jobs,record,_=setup_bundle(tmp_path)
    with TestClient(create_app(initial,jobs)) as client:
        response=client.get(record['preview_url']+'api/checklist')
        assert response.status_code==200
        report=response.json()
        stages={s['id']:s for s in report['stages']}
        assert stages['input']['status']=='missing'
        assert stages['views']['status']=='missing'
        assert stages['update']['status']=='missing'
        assert all(stages[k]['status']=='passed' for k in ('candidate','publication','query','offline'))
        assert report['publication_id']==record['id']
        assert report['production_ready'] is False and report['robot_ready'] is False
        assert len(report['gaps'])==5
        # The common distribution gate resolves invalid/missing IDs before checklist routing.
        assert client.get('/publications/preview-not-found/api/checklist').status_code==404
        (jobs.root/'publications'/record['id']/'agent.npz').write_bytes(b'changed')
        assert client.get(record['preview_url']+'api/checklist').status_code==409


def test_saved_update_evidence_requires_exact_publication_and_package(tmp_path):
    _,jobs,record,bundle=setup_bundle(tmp_path)
    pubs=PreviewPublications(jobs); path=tmp_path/'evidence.json'
    evidence={'new_publication':record,'after':{'publication_id':record['id'],'package_sha256':sha(bundle)},
              'online_new':{'publication_id':record['id']},
              **{k:True for k in ('download_only_did_not_activate','old_session_unchanged',
                                 'old_publication_unchanged','stale_activation_refused',
                                 'socket_creation_disabled_during_switch')}}
    def status():
        path.write_text(json.dumps(evidence),encoding='utf-8')
        return checklist(pubs,record['id'],path)['stages'][-1]['status']
    assert status()=='recorded'
    evidence['after']['package_sha256']='wrong'
    assert status()=='missing'
    evidence['after']['package_sha256']=sha(bundle)
    evidence['new_publication']={**record,'id':'other-publication'}
    assert status()=='missing'
    evidence['new_publication']=record
    evidence['old_session_unchanged']=False
    assert status()=='failed'
    path.write_bytes(b'invalid')
    assert checklist(pubs,record['id'],path)['stages'][-1]['status']=='failed'


def test_read_only_check_does_not_change_selection_or_publication(tmp_path):
    _,jobs,record,_=setup_bundle(tmp_path)
    pubs=PreviewPublications(jobs)
    selection=jobs.selection()
    before={p.name:p.read_bytes() for p in (pubs.root/record['id']).iterdir()}
    checklist(pubs,record['id'])
    assert jobs.selection()==selection
    assert {p.name:p.read_bytes() for p in (pubs.root/record['id']).iterdir()}==before
