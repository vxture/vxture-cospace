"""Pinned historical-inspection fixture; source and voxel are synthetic."""
import hashlib
import json

from packages.service.release_sample import build_release_sample
from packages.views.agent.voxel_sample import build_voxel_sample


def build_consumption_sample(mode='historical'):
    def profile(doc):
        doc['mode']=mode
        doc['freshness']['max_age_s']=None if mode=='historical' else 3600
    source=build_release_sample({'profile.json':profile})
    files,pin=build_voxel_sample(source)
    release=json.loads(source['release.json'])
    request={
        'schema_version':'cospace.consumption/0.1','kind':'request','request_id':'synthetic-request-1',
        'source':pin['source'],'package_sha256':hashlib.sha256(files['agent-voxel.json']).hexdigest(),
        'profile_ref':{k:release['quality_profile'][k] for k in ('id','sha256')},
        'frame_id':pin['frame_id'],'purpose':'spatial_query','mode':mode,'max_age_s':None,
        'items':[{'item_id':'free','point':[1.5,.5,.5]},
                 {'item_id':'conflict','point':[4.5,.5,.5]},
                 {'item_id':'missing','point':[5.5,5.5,.5]},
                 {'item_id':'outside','point':[10,0,0]},
                 {'item_id':'bad-point','point':['bad',0,0]}]}
    return source,files,request
