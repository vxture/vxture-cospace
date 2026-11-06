"""Reproducible object move and whole coverage-resource replacement fixture."""
import json

from packages.service.release_sample import build_release_sample
from packages.spatial.changes import canonical, digest, object_digest


def build_change_sample():
    source=build_release_sample()
    release=json.loads(source['release.json'])
    truth=json.loads(source[release['source_truth']['path']])
    objects=json.loads(source[truth['objects']['path']])
    resources={'evidence/change.json':canonical({'notice':'synthetic change observation, not independent field verification'}),
               'replacement/coverage.json':canonical({'notice':'changed synthetic coverage placeholder, not a decoded partition'})}
    def ref(identity,path):
        raw=resources[path]
        return {'id':identity,'path':path,'sha256':digest(raw),'bytes':len(raw)}
    moved={**objects['instances'][0],'anchor':[3,2,0]}
    change={
        'schema_version':'cospace.spatial-change/0.1','change_id':'change-001','scene_id':release['scene_id'],'data_kind':'synthetic',
        'base':{'release_id':release['id'],'release_sha256':digest(source['release.json']),
                'truth_id':truth['id'],'truth_sha256':release['source_truth']['sha256']},
        'new_truth_id':'candidate-truth-002','new_objects_id':'objects-v2',
        'evidence':[ref('change-evidence-001','evidence/change.json')],
        'operations':[{'op':'object.replace','object':moved,'expected_object_sha256':object_digest(objects['instances'][0])},
                      {'op':'resource.replace','role':'coverage','expected_sha256':truth['coverage']['sha256'],
                       'replacement':ref('partition-v2','replacement/coverage.json')}]}
    return source,change,resources
