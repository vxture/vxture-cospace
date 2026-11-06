import json
import socket
import subprocess
import sys
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from fastapi.testclient import TestClient
from packages.spatial.preview_range import surface_range
from packages.views.agent.preview_offline import OfflinePreview,sha
from packages.service.preview_publications import PreviewPublications
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_offline import setup_bundle


def select(cells,bounds,limit=1024,frame='anchor'):
    return surface_range(cells,.1,bounds,frame,'anchor',limit)


def test_half_open_centers_negative_and_decimal_boundaries():
    cells={(x,0,0) for x in range(-3,4)}
    result=select(cells,[[-.15,0,0],[.15,.1,.1]])
    assert result['cell_indices']==[[-2,0,0],[-1,0,0],[0,0,0]]
    assert result['result_complete'] is True and result['matched_cells']==3
    # A point may intersect an edge of a cell without selecting that cell center.
    assert select(cells,[[.01,.01,.01],[.04,.04,.04]])['cell_indices']==[]


def test_order_is_deterministic_limit_has_no_partial_result_or_false_unknown():
    cells={(2,0,0),(-1,0,0),(0,0,0)}
    bounds=[[-1,-1,-1],[1,1,1]]
    full=select(cells,bounds,3)
    assert full['cell_indices']==[[-1,0,0],[0,0,0],[2,0,0]]
    limited=select(cells,bounds,2)
    assert limited['status']=='limit_exceeded' and limited['result_complete'] is False
    assert limited['matched_cells']==3 and limited['returned_cells']==0 and limited['cell_indices']==[]
    assert limited['unlisted_state'] is None
    empty=select(cells,[[10,10,10],[11,11,11]])
    assert empty['result_complete'] and empty['unlisted_state']=='unknown' and empty['coverage']=='surface_evidence_only'


def test_adjacent_ranges_partition_centers_without_overlap_or_dense_enumeration():
    cells={(i,0,0) for i in range(-10,10)}
    whole=select(cells,[[-1_000_000,-1_000_000,-1_000_000],[1_000_000,1_000_000,1_000_000]])
    left=select(cells,[[-1,-1,-1],[0,1,1]])
    right=select(cells,[[0,-1,-1],[1,1,1]])
    assert left['cell_indices']+right['cell_indices']==whole['cell_indices']
    assert not {tuple(v) for v in left['cell_indices']} & {tuple(v) for v in right['cell_indices']}


@pytest.mark.parametrize('bounds,frame,limit',[
    ([[0,0,0],[0,1,1]],'anchor',1),
    ([[1,0,0],[0,1,1]],'anchor',1),
    ([[0,0,0],[float('inf'),1,1]],'anchor',1),
    ([[0,0,0],[float('nan'),1,1]],'anchor',1),
    ([[0,0,0],[1_000_001,1,1]],'anchor',1),
    ([[0,0,0],[10**1000,1,1]],'anchor',1),
    ([[False,0,0],[1,1,1]],'anchor',1),
    ([['0',0,0],[1,1,1]],'anchor',1),
    ([[0,0],[1,1,1]],'anchor',1),
    ([[0,0,0],[1,1,1]],'other',1),
    ([[0,0,0],[1,1,1]],'anchor',0),
    ([[0,0,0],[1,1,1]],'anchor',4097),
    ([[0,0,0],[1,1,1]],'anchor',True),
    ([[0,0,0],[1,1,1]],'anchor',1.0),
])
def test_invalid_range_is_rejected(bounds,frame,limit):
    with pytest.raises(ValueError):select({(0,0,0)},bounds,limit,frame)


def test_fixed_online_offline_equality_and_selection_change(tmp_path,monkeypatch):
    initial,jobs,record,bundle=setup_bundle(tmp_path)
    requests=[{'bounds_m':[[-1,-1,-1],[1,1,1]],'frame_id':'anchor','limit':2},
              {'bounds_m':[[-1,-1,-1],[1,1,1]],'frame_id':'anchor','limit':1},
              {'bounds_m':[[2,2,2],[3,3,3]],'frame_id':'anchor','limit':1}]
    with TestClient(create_app(initial,jobs)) as client:
        online=[]
        schema=json.loads(Path('contracts/schemas/preview-range-v0.1.schema.json').read_bytes())
        Draft202012Validator.check_schema(schema)
        validator=Draft202012Validator(schema)
        for request in requests:
            validator.validate(request)
            response=client.post(record['preview_url']+'api/query-range',json=request)
            assert response.status_code==200,response.text
            result=response.json();validator.validate(result);online.append(result)
        assert list(validator.iter_errors(online[1]|{'result_complete':True}))
        jobs.select('build-two',1)
        assert client.post(record['preview_url']+'api/query-range',json=requests[0]).json()==online[0]
        for change in [{'frame_id':'map'},{'limit':True},{'limit':'2'},{'extra':1},{'bounds_m':[[False,0,0],[1,1,1]]}]:
            assert client.post(record['preview_url']+'api/query-range',json=requests[0]|change).status_code==422
    def denied(*args,**kwargs):raise AssertionError('network disabled')
    monkeypatch.setattr(socket,'socket',denied)
    offline=OfflinePreview(bundle,record['id'],sha(bundle))
    assert [offline.query_range(**r) for r in requests]==online
    assert online[0]['publication_id']==record['id'] and online[0]['robot_ready'] is False
    assert online[0]['cell_indices']==[[-1,0,0],[1,2,3]]
    assert online[1]['result_complete'] is False and online[2]['unlisted_state']=='unknown'


def test_cli_range_and_mode_validation(tmp_path):
    _,_,record,bundle=setup_bundle(tmp_path)
    path=tmp_path/'offline.zip';path.write_bytes(bundle)
    command=[sys.executable,'-m','experiments.scripts.query_preview_offline',str(path),'--publication',record['id'],'--sha256',sha(bundle)]
    response=subprocess.run(command+['--bounds','-1','-1','-1','1','1','1','--frame-id','anchor','--limit','2'],capture_output=True,text=True,timeout=15)
    assert response.returncode==0,response.stderr
    assert json.loads(response.stdout)['returned_cells']==2
    exceeded=subprocess.run(command+['--bounds','-1','-1','-1','1','1','1','--frame-id','anchor','--limit','1'],capture_output=True,text=True,timeout=15)
    assert exceeded.returncode==3 and json.loads(exceeded.stdout)['result_complete'] is False
    for args in [['--bounds','0','0','0','1','1','1'],['--point','0','0','0','--limit','2']]:
        assert subprocess.run(command+args,capture_output=True,timeout=15).returncode==2


def test_mutated_publication_cannot_serve_range(tmp_path):
    initial,jobs,record,_=setup_bundle(tmp_path)
    pubs=PreviewPublications(jobs);(pubs.root/record['id']/'agent.npz').write_bytes(b'changed')
    with TestClient(create_app(initial,jobs)) as client:
        assert client.post(record['preview_url']+'api/query-range',json={'bounds_m':[[0,0,0],[1,1,1]],'frame_id':'anchor'}).status_code==409
