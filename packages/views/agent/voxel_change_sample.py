"""Synthetic add/replace/remove exercise over F05 chunks."""
from packages.spatial.changes import digest
from packages.service.sample import read_json
from packages.views.agent.voxel_sample import build_voxel_sample


def build_voxel_change_sample():
    files,pin=build_voxel_sample()
    manifest=read_json(files['agent-voxel.json'])
    old={tuple(c['index']):c['member']['sha256'] for c in manifest['chunks']}
    resources={'evidence/change.txt':b'synthetic observation; not an independent survey',
               'input/add.u8':bytes([2]*25),'input/replace.u8':bytes([1]*25)}
    def ref(path):
        return {'path':path,'bytes':len(resources[path]),'sha256':digest(resources[path])}
    change={'schema_version':'cospace.voxel-change/0.1','change_id':'voxel-change-001','data_kind':'synthetic',
        'base_package_id':manifest['package_id'],'base_package_sha256':digest(files['agent-voxel.json']),
        'candidate_package_id':'voxel-candidate-002','evidence':[ref('evidence/change.txt')],
        'operations':[
            {'op':'chunk.add','index':[1,1,0],'expected_absent':True,'replacement':ref('input/add.u8')},
            {'op':'chunk.replace','index':[0,0,0],'expected_sha256':old[(0,0,0)],'replacement':ref('input/replace.u8')},
            {'op':'chunk.remove','index':[1,0,0],'expected_sha256':old[(1,0,0)]}]}
    return files,pin,change,resources
