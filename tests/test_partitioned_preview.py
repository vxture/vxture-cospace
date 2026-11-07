import json
from pathlib import Path
import socket
import subprocess
import sys
import zipfile
import numpy as np
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from packages.construction.preview_model import digest
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.partitioned_preview import (
    PartitionIndex,PartitionedPreview,export_partitions,sha,encoded)
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_publications import fixture
from test_preview_offline import pack


def prepared(tmp_path,cells=None):
    initial,jobs=fixture(tmp_path)
    if cells is not None:
        root=jobs.root/'build-one'/'output'
        np.savez_compressed(root/'agent.npz',cells=np.asarray(cells,dtype=np.int64))
        manifest=json.loads((root/'model.json').read_bytes())
        manifest['members']['agent.npz']={'sha256':digest(root/'agent.npz'),'bytes':(root/'agent.npz').stat().st_size}
        manifest['agent_view']['surface_cells']=len(cells)
        (root/'model.json').write_text(json.dumps(manifest))
    jobs.select('build-one',0);pubs=PreviewPublications(jobs);record=pubs.publish('build-one',1)
    _,model=pubs.read(record['id']);raw,info=export_partitions(record,model)
    path=tmp_path/'partitions.zip';path.write_bytes(raw)
    return initial,jobs,record,model,path,info


def reader(value):
    _,_,record,_,path,info=value
    return PartitionedPreview(path,record['id'],info['index_sha256'],record.get('space_id'))


def contents(path):
    with zipfile.ZipFile(path) as archive:return {n:archive.read(n) for n in archive.namelist()}


def test_deterministic_export_reconstructs_exactly_and_schema(tmp_path):
    cells=[(x,y,0) for x in range(-10,110) for y in range(100)]
    value=prepared(tmp_path,cells);_,_,record,model,path,info=value
    raw,again=export_partitions(record,model)
    assert raw==path.read_bytes() and again==info
    files=contents(path);doc=json.loads(files['index.json'])
    rebuilt=sorted(tuple(map(int,row)) for p in doc['partitions'] for row in np.frombuffer(files[p['id']+'.bin'],dtype='<i8').reshape(-1,3))
    assert rebuilt==sorted(cells) and sha(encoded(rebuilt))==doc['canonical_cells_sha256']
    assert all(p['cells']<=4096 for p in doc['partitions']) and len(doc['partitions'])>2
    schema=json.loads(Path('contracts/schemas/partitioned-agent-v0.1.schema.json').read_bytes())
    assert schema==PartitionIndex.model_json_schema()
    Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(doc)
    assert 'agent.npz' not in files and 'spatial.npz' not in files


def test_lazy_queries_match_whole_model_without_network(tmp_path,monkeypatch):
    value=prepared(tmp_path,[(-257,0,0),(-1,0,0),(0,0,0),(256,0,0),(512,0,0)])
    _,jobs,record,model,_,_=value;offline=reader(value)
    def forbidden(*args,**kwargs):raise AssertionError('no network')
    monkeypatch.setattr(socket,'socket',forbidden)
    for point in ([.05,.05,.05],[-.05,.05,.05],[20,0,0]):
        response=offline.query(point,'anchor');expected=model.query(point)
        assert all(response[k]==v for k,v in expected.items() if k!='profile')
        assert response['partition_read']['read']<=1<response['partition_read']['total']
    for bounds in ([[0,0,0],[.1,.1,.1]],[[-.15,0,0],[.15,.1,.1]],[[.01,.01,.01],[.04,.04,.04]]):
        result=offline.query_range(bounds,'anchor');expected=model.query_range(bounds,'anchor')
        assert all(result[k]==v for k,v in expected.items() if k!='profile')
        assert result['partition_read']['read']<result['partition_read']['total']
    assert offline.last_read==[] # no integer cell center is in this tiny range
    jobs.select('build-two',1)
    assert offline.query([.05,.05,.05],'anchor')['publication_id']==record['id']


def test_read_scope_does_not_claim_untouched_data_verified(tmp_path):
    value=prepared(tmp_path,[(0,0,0),(512,0,0)]);offline=reader(value)
    files=contents(value[4]);files['p00001.bin']=b'x'*24;value[4].write_bytes(pack(files))
    assert offline.query([.05,.05,.05],'anchor')['state']=='surface_candidate'
    assert offline.last_read==['p00000']
    with pytest.raises(ValueError,match='member_integrity'):offline.query([51.25,.05,.05],'anchor')
    files.pop('p00001.bin');value[4].write_bytes(pack(files))
    with pytest.raises(ValueError,match='archive_members'):offline.query([0,0,0],'anchor')


@pytest.mark.parametrize('mode',['digest','publication','space','frame','invalid_point'])
def test_explicit_binding_and_queries_refused(tmp_path,mode):
    value=prepared(tmp_path);_,_,record,_,path,info=value
    with pytest.raises(ValueError):
        offline=PartitionedPreview(path,'preview-'+'0'*16 if mode=='publication' else record['id'],
            '0'*64 if mode=='digest' else info['index_sha256'],'space-foreign' if mode=='space' else None)
        if mode=='frame':offline.query([0,0,0],'different')
        if mode=='invalid_point':offline.query([True,0,0],'anchor')


@pytest.mark.parametrize('change',['source','index','extra','length','duplicate'])
def test_archive_tampering_and_reuse_refused(tmp_path,change):
    value=prepared(tmp_path);offline=reader(value);files=contents(value[4])
    if change=='source':files['model.json']=b'x'*len(files['model.json'])
    if change=='index':files['index.json']=files['index.json'].replace(b'anchor',b'other_')
    if change=='extra':files['../outside.bin']=b'x'
    if change=='length':files['p00000.bin']+=b'x'
    value[4].write_bytes(pack(files))
    if change=='duplicate':
        with zipfile.ZipFile(value[4],'a') as archive:
            with pytest.warns(UserWarning):archive.writestr('index.json',files['index.json'])
    with pytest.raises(ValueError):offline.query([0,0,0],'anchor')


def test_index_semantics_reject_overlap_count_and_source_binding(tmp_path):
    value=prepared(tmp_path);files=contents(value[4]);doc=json.loads(files['index.json'])
    for changed in (doc|{'total_cells':3},doc|{'robot_ready':True},doc|{'robot_ready':0},
                    doc|{'max_tile_cells':4096.0},doc|{'resolution_m':float('nan')}):
        with pytest.raises(ValueError):PartitionIndex.model_validate(changed)
    doc['partitions'][1]['cell_bounds']=doc['partitions'][0]['cell_bounds']
    with pytest.raises(ValueError,match='overlap'):PartitionIndex.model_validate(doc)
    doc=json.loads(files['index.json']);doc['source_agent_sha256']='0'*64
    files['index.json']=json.dumps(doc).encode();value[4].write_bytes(pack(files))
    with pytest.raises(ValueError,match='source_binding'):
        PartitionedPreview(value[4],value[2]['id'],sha(files['index.json']))


def test_read_and_result_budgets_return_no_partial_or_false_unknown(tmp_path,monkeypatch):
    value=prepared(tmp_path,[(i*256,0,0) for i in range(65)]);offline=reader(value)
    result=offline.query_range([[-1,-1,-1],[2000,1,1]],'anchor',4096)
    assert result['status']=='partition_budget_exceeded' and result['partition_read']['read']==0
    assert result['matched_cells'] is None and result['unlisted_state'] is None and not result['result_complete']
    assert result['cell_indices']==[]
    limited=offline.query_range([[0,0,0],[100,1,1]],'anchor',1)
    assert limited['status']=='limit_exceeded' and limited['matched_cells']==4
    assert limited['cell_indices']==[] and limited['unlisted_state'] is None
    monkeypatch.setattr('packages.views.agent.partitioned_preview.MAX_QUERY_CELLS',1)
    assert offline.query_range([[0,0,0],[100,1,1]],'anchor')['status']=='partition_budget_exceeded'


def test_export_rejects_source_cell_disagreement_and_mutation(tmp_path):
    _,_,record,model,_,_=prepared(tmp_path)
    model.cells.add((0,0,0))
    with pytest.raises(ValueError,match='cell_mismatch'):export_partitions(record,model)
    (model.root/'agent.npz').write_bytes(b'changed')
    with pytest.raises(ValueError,match='source_changed'):export_partitions(record,model)


def test_consumer_validates_decoded_cells_even_with_matching_digest(tmp_path):
    value=prepared(tmp_path,[(0,0,0),(1,0,0)]);files=contents(value[4]);doc=json.loads(files['index.json'])
    for cells in ([(1,0,0),(0,0,0)],[(0,0,0),(0,0,0)],[(0,0,0),(9,0,0)]):
        files['p00000.bin']=encoded(cells);doc['partitions'][0]['sha256']=sha(files['p00000.bin'])
        files['index.json']=json.dumps(doc).encode();value[4].write_bytes(pack(files))
        offline=PartitionedPreview(value[4],value[2]['id'],sha(files['index.json']))
        with pytest.raises(ValueError,match='cell_binding'):offline.query([0,0,0],'anchor')


def test_declared_budgets_rejected_before_partition_decode(tmp_path,monkeypatch):
    value=prepared(tmp_path);offline=reader(value)
    monkeypatch.setattr('packages.views.agent.partitioned_preview.MAX_BYTES',100)
    with pytest.raises(ValueError,match='package_budget'):offline.query([0,0,0],'anchor')


def test_http_export_failures_do_not_expose_local_paths(tmp_path,monkeypatch):
    value=prepared(tmp_path)
    def denied(*args):raise OSError('private path must not leak')
    monkeypatch.setattr('experiments.scripts.serve_nyu_flow_preview.export_partitions',denied)
    with TestClient(create_app(value[0],value[1])) as client:
        for suffix in ('partitions.json','partitions.zip'):
            response=client.get(value[2]['preview_url']+suffix)
            assert response.status_code==409 and response.json()['detail']=='partition_delivery_unavailable'


def test_http_and_offline_cli(tmp_path):
    value=prepared(tmp_path);initial,jobs,record,_,path,info=value
    with TestClient(create_app(initial,jobs)) as client:
        response=client.get(record['preview_url']+'partitions.zip')
        assert response.status_code==200 and response.content==path.read_bytes()
        assert response.headers['x-cospace-index-sha256']==info['index_sha256']
        assert response.headers['cache-control']=='no-store'
        metadata=client.get(record['preview_url']+'partitions.json').json()
        assert metadata==info|{'download_url':record['preview_url']+'partitions.zip'}
    command=[sys.executable,'-m','experiments.scripts.query_partitioned_preview',str(path),
        '--publication',record['id'],'--index-sha256',info['index_sha256'],'--legacy','--frame-id','anchor']
    for args,code in [(['--point','-.05','.05','.05'],0),(['--bounds','-1','-1','-1','1','1','1','--limit','1'],3),
                       (['--point','0','0','0','--limit','1'],2),(['--point','nan','0','0'],2)]:
        result=subprocess.run(command+args,capture_output=True,text=True,timeout=15)
        assert result.returncode==code,result.stderr
        if code!=2:assert json.loads(result.stdout)['result_complete']==(code==0)
