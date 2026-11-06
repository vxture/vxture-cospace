import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from packages.construction.preview_model import surface_cells,PreviewModel,digest
from experiments.scripts.serve_nyu_flow_preview import create_app


def make_preview(tmp_path):
    np.savez_compressed(tmp_path/'agent.npz',cells=np.array([[-1,0,0],[1,2,3]]))
    np.savez_compressed(tmp_path/'spatial.npz',points=np.array([[0.,0.,2.]]),colors=np.array([[40,80,120]],dtype='u1'))
    (tmp_path/'index.html').write_text('preview')
    m={'profile':'cospace.real-model-preview/0.1','id':'fixture','frame_id':'anchor',
       'agent_view':{'resolution_m':.1},'members':{name:{'sha256':digest(tmp_path/name)}
       for name in ['agent.npz','spatial.npz']}}
    (tmp_path/'model.json').write_text(json.dumps(m))
    return tmp_path


def test_surface_voxelization_and_unknown_are_distinct(tmp_path):
    cells=surface_cells(np.array([[-.01,.01,.01],[-.09,.09,.09],[.1,.2,.3]]),.1)
    assert [-1,0,0] in cells.tolist() and len(cells)==2
    model=PreviewModel(make_preview(tmp_path))
    assert model.query([-.05,.05,.05])['state']=='surface_candidate'
    assert model.query([0,0,0])['state']=='unknown'
    assert model.query([100,100,100])['robot_ready'] is False


def test_artifact_mutation_rejected(tmp_path):
    root=make_preview(tmp_path); (root/'agent.npz').write_bytes(b'changed')
    with pytest.raises(ValueError,match='integrity'): PreviewModel(root)


@pytest.mark.parametrize('problem',['human_source','agent_source','missing_human_artifact'])
def test_dual_views_cannot_mix_geometry_sources(tmp_path,problem):
    root=make_preview(tmp_path)
    (root/'human.ply').write_bytes(b'fixed human geometry')
    manifest=json.loads((root/'model.json').read_bytes())
    manifest['members']['human.ply']={'sha256':digest(root/'human.ply')}
    source=manifest['members']['spatial.npz']['sha256']
    manifest['human_view']={'path':'human.ply','source_model_sha256':source}
    manifest['agent_view'].update(path='agent.npz',source_model_sha256=source)
    (root/'model.json').write_text(json.dumps(manifest))
    PreviewModel(root)
    if problem=='human_source':manifest['human_view']['source_model_sha256']='0'*64
    elif problem=='agent_source':manifest['agent_view']['source_model_sha256']='1'*64
    else:manifest['human_view']['path']='missing.ply'
    (root/'model.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='dual_view_source_mismatch'):PreviewModel(root)


def test_http_matches_offline_query_and_rejects_bad_point(tmp_path):
    root=make_preview(tmp_path); model=PreviewModel(root)
    with TestClient(create_app(root)) as client:
        p=[-.05,.05,.05]
        assert client.post('/api/query',json={'point_m':p}).json()==model.query(p)
        assert client.post('/api/query',json={'point_m':[0,0]}).status_code==422
        assert client.get('/api/preview').json()['service_state']=='preview_served'
        assert client.get('/').status_code==200


def test_workbench_thumbnail_and_local_origin_access(tmp_path):
    root=make_preview(tmp_path)
    with TestClient(create_app(root)) as client:
        thumbnail=client.get('/api/thumbnail')
        assert thumbnail.status_code==200 and thumbnail.headers['content-type']=='image/png'
        assert thumbnail.content.startswith(b'\x89PNG\r\n\x1a\n')
        allowed=client.get('/api/preview',headers={'Origin':'http://127.0.0.1:8766'})
        assert allowed.headers['access-control-allow-origin']=='http://127.0.0.1:8766'
        denied=client.get('/api/preview',headers={'Origin':'https://example.com'})
        assert 'access-control-allow-origin' not in denied.headers
