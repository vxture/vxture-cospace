"""Independent synthetic voxel fixture, not voxelization of F04 placeholder geometry."""
import hashlib
import json

from packages.service.release_sample import build_release_sample
from packages.views.agent.voxel import pinned_voxel_source


def build_voxel_sample(source=None):
    source = build_release_sample() if source is None else source
    pin = pinned_voxel_source(source, now='2026-10-28T00:30:00Z')
    files, chunks = {}, []
    for index in ([0,0,0],[1,0,0],[0,1,0]):
        payload = bytes([0,1,2,3,4] + [1]*20)
        name = 'chunks/' + '-'.join(map(str,index)) + '.u8'
        files[name] = payload
        chunks.append({'index':index,'member':{'path':name,'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}})
    manifest = {
        'schema_version':'cospace.agent-voxel/0.1','package_id':'synthetic-voxel-001','data_kind':'synthetic','derivation':'synthetic_fixture_not_voxelized',
        'source':pin['source'],'frame_id':pin['frame_id'],'origin_m':pin['bounds'][0],
        'resolution_m':1,'dimensions':[10,10,1],'chunk_shape':[5,5,1],'index_order':'x_fastest',
        'components':[{'id':'occupancy','role':'occupancy','encoding':'cospace.occupancy-u8/0.1','required':True,'depends_on':[]}],
        'chunks':chunks}
    files['agent-voxel.json'] = json.dumps(manifest, sort_keys=True, separators=(',',':')).encode('utf-8')
    return files,pin
