from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from packages.data.scene_pointcloud_intake import digest, intake, local_xyz


DTYPE = np.dtype([('X', '<i4'), ('Y', '<i4'), ('Z', '<i4'), ('intensity', '<u2'),
                  ('flags', 'u1'), ('classification', 'u1'), ('angle', 'i1'),
                  ('user', 'u1'), ('source', '<u2'), ('red', '<u2'), ('green', '<u2'), ('blue', '<u2')])


def fixture(tmp_path, name='one.laz', shift=0):
    path = tmp_path/name
    path.write_bytes(b'opaque original LAS payload '+name.encode())
    records = np.zeros(7, dtype=DTYPE)
    records['X'] = [0, 1000, 2000, 21000, 22000, 40000, 41000]
    records['Y'] = [0, -1000, 2000, 3000, 1000, 0, 0]
    records['Z'] = [-1000, 0, 1000, 2000, 0, 0, 0]
    records['red'] = np.arange(7)*1000
    records['intensity'] = np.arange(7)+500
    records['classification'] = [1, 2, 3, 4, 5, 6, 7]
    scales = np.array([.001]*3)
    offsets = np.array([583000.+shift, 4794000., 0.])
    xyz = np.column_stack([records[n] for n in ('X', 'Y', 'Z')])*scales+offsets
    header = SimpleNamespace(point_format=SimpleNamespace(id=2, size=26),
                             mins=xyz.min(axis=0), maxs=xyz.max(axis=0),
                             scales=scales, offsets=offsets, point_count=len(records))
    return path, records, header


def opener_at(fixtures, on_chunk=None, shorten=False):
    @contextmanager
    def opener(path):
        _, records, header = fixtures[Path(path).name]
        def chunks(count):
            for start in range(0, len(records)-(1 if shorten else 0), count):
                end = min(start+count, len(records)-(1 if shorten else 0))
                if on_chunk:
                    on_chunk()
                yield SimpleNamespace(array=records[start:end])
        yield SimpleNamespace(header=header, chunk_iterator=chunks)
    return opener


def test_full_records_ordinals_tiles_sources_and_attachment_preserved(tmp_path):
    one = fixture(tmp_path)
    two = fixture(tmp_path, 'two.laz', 100)
    ifc = tmp_path/'station.ifc'; ifc.write_bytes(b'ISO-10303-21; preserved attachment')
    output = tmp_path/'result'
    report = intake([one[0], two[0]], output, scene_name='Station', ifc=ifc,
                    chunk_points=3, tile_size=20, unit_basis='assumed_metre_for_flow_validation',
                    opener=opener_at({'one.laz': one, 'two.laz': two}))
    assert report['total_points'] == 14 and not report['merged']
    assert not report['unit_verified'] and not report['alignment_verified']
    assert not report['production_ready'] and report['sampling'] == 'none'
    for source, original in zip(report['sources'], (one, two)):
        restored = np.empty(7, dtype=DTYPE); seen=[]
        for shard in source['shards']:
            path=output/shard['path']; assert digest(path)==shard['sha256']
            with np.load(path, allow_pickle=False) as data:
                ids=data['source_indices']; points=data['records']
                assert len(points)<=3
                restored[ids]=points; seen.extend(ids.tolist())
                xyz=local_xyz(points,source,report['origin'])
                assert (np.floor(xyz/20).astype(int)==shard['tile']).all()
        assert sorted(seen)==list(range(7))
        assert restored.tobytes()==original[1].tobytes()
        assert source['discarded_points']==0
    assert (output/'attachments/station.ifc').read_bytes()==ifc.read_bytes()
    assert json.loads((output/'intake-state.json').read_bytes())['state']=='complete'


@pytest.mark.parametrize('options',[
    {'chunk_points':0}, {'chunk_points':True}, {'chunk_points':250001},
    {'tile_size':0}, {'tile_size':float('nan')}, {'tile_size':float('inf')},
    {'unit_basis':'unknown'}, {'scene_name':' '},
])
def test_invalid_parameters_leave_no_output(tmp_path, options):
    one=fixture(tmp_path)
    args=dict(scene_name='Station',unit_basis='assumed_metre_for_flow_validation');args.update(options)
    with pytest.raises(ValueError):
        intake([one[0]],tmp_path/'output',opener=opener_at({'one.laz':one}),**args)
    assert not (tmp_path/'output').exists()


def test_duplicate_and_existing_output_rejected(tmp_path):
    one=fixture(tmp_path); args=dict(scene_name='s',unit_basis='verified_metre',opener=opener_at({'one.laz':one}))
    with pytest.raises(ValueError,match='duplicate'):
        intake([one[0],one[0]],tmp_path/'output',**args)
    with pytest.raises(ValueError,match='exclusive'):
        intake([one[0]],tmp_path,**args)
    assert one[0].is_file()


@pytest.mark.parametrize('problem',['short','changed','bounds','format','budget'])
def test_partial_failure_never_publishes_scene_manifest(tmp_path,problem,monkeypatch):
    one=fixture(tmp_path)
    if problem=='bounds':one[2].maxs[0]+=1
    if problem=='format':one[2].point_format.id=3
    if problem=='budget':monkeypatch.setattr('packages.data.scene_pointcloud_intake.MAX_SHARDS',1)
    callback=(lambda:one[0].write_bytes(b'changed')) if problem=='changed' else None
    opener=opener_at({'one.laz':one},callback,shorten=problem=='short')
    output=tmp_path/'output'
    with pytest.raises(ValueError):
        intake([one[0]],output,scene_name='s',unit_basis='verified_metre',chunk_points=3,opener=opener)
    assert not (output/'scene.json').exists()
    if output.exists():assert json.loads((output/'intake-state.json').read_bytes())['state']=='failed'


def test_early_source_changed_during_later_source_is_detected(tmp_path):
    one=fixture(tmp_path)
    two=fixture(tmp_path,'two.laz',100)
    base=opener_at({'one.laz':one,'two.laz':two})
    calls={}
    @contextmanager
    def changing(path):
        name=Path(path).name;calls[name]=calls.get(name,0)+1
        if name=='two.laz' and calls[name]==2:
            one[0].write_bytes(b'late mutation')
        with base(path) as value:yield value
    with pytest.raises(ValueError,match='source_changed'):
        intake([one[0],two[0]],tmp_path/'result',scene_name='s',
               unit_basis='assumed_metre_for_flow_validation',opener=changing)
    assert not (tmp_path/'result/scene.json').exists()
