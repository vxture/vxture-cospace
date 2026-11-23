"""Synthetic exact-point capacity probe; coordinates are not survey evidence."""
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np

from packages.construction.model_display import ModelDisplays, encoded


def coordinates(indices):
    return np.column_stack((500000 + (indices % 10000) * .01,
                            4000000 + ((indices // 10000) % 2000) * .01,
                            18 + (indices % 17) * .001))


def probe(root, count):
    output = Path(root) / 'build-exact-probe/output'
    output.mkdir(parents=True)
    path = output / 'spatial.npz'
    header = io.BytesIO()
    np.lib.format.write_array_header_1_0(header, dict(descr='<f8',fortran_order=False,shape=(count,3)))
    with ZipFile(path,'w',compression=ZIP_DEFLATED) as archive, archive.open('points.npy','w',force_zip64=True) as target:
        target.write(header.getvalue())
        for start in range(0,count,25000):
            target.write(coordinates(np.arange(start,min(start+25000,count))).astype('<f8').tobytes())
    digest = sha256()
    with path.open('rb') as stream:
        while block := stream.read(262144):
            digest.update(block)
    source = digest.hexdigest()
    model = {'profile':'cospace.real-model-preview/0.1','id':'build-exact-probe','unit':'m',
             'frame_id':'synthetic/local','axes':['right','forward','up'],'construction':{'model_points':count},
             'members':{'spatial.npz':{'sha256':source}},
             'human_view':{'source_model_sha256':source},'agent_view':{'source_model_sha256':source}}
    raw = encoded(model)
    (output/'model.json').write_bytes(raw)
    (output.parent/'job.json').write_bytes(encoded({'id':model['id'],'state':'succeeded'}))
    displays = ModelDisplays(SimpleNamespace(root=Path(root),directory=None))
    exact = displays.exact
    key = (sha256(raw).hexdigest(),source)
    start = time.perf_counter()
    assert exact.read('candidate',model['id'],*key,point_index=0)['state']=='preparing'
    exact.scan()
    build_seconds = time.perf_counter()-start
    timings = []
    for index in (0, count//2, count-1):
        expected = coordinates(np.array([index]))[0].tolist()
        start = time.perf_counter()
        point = exact.read('candidate',model['id'],*key,point_index=index)['points'][0]
        assert point['point_index']==index and point['anchor_m']==expected
        result = exact.read('candidate',model['id'],*key,point=expected,radius_m=.001)
        assert result['state']=='ready' and any(p['point_index']==index for p in result['points'])
        timings.append((time.perf_counter()-start)*1000)
    print(json.dumps({'points':count,'index_bytes':exact.path(key).stat().st_size,'build_seconds':build_seconds,
                      'paired_query_ms':timings,'original_double_coordinates_preserved':True}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--points',type=int,default=1_000_000)
    parser.add_argument('--root',type=Path)
    args = parser.parse_args()
    if not 1000<=args.points<=20_000_000:
        parser.error('explicit capacity budget is 1000..20000000 points')
    if args.root:
        allowed = (Path(__file__).resolve().parents[2] / 'var').resolve()
        destination = args.root.resolve()
        if destination == allowed or not destination.is_relative_to(allowed):
            parser.error('--root must be a new task directory inside the repository var directory')
        probe(destination,args.points)
    else:
        with tempfile.TemporaryDirectory() as folder:
            probe(Path(folder)/'jobs',args.points)


if __name__=='__main__':
    main()
