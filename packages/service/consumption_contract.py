"""F06a bounded historical inspection; operational calls always fail closed."""
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from packages.service.release_contract import inspect_release_snapshot
from packages.service.sample import read_json
from packages.spatial.quality_contract import utc
from packages.views.agent.voxel import VoxelSession, finite_number, pinned_voxel_source

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/schemas/consumption-v0.1.schema.json'


def check(document, kind):
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    if list(Draft202012Validator({'$defs':schema['$defs'],'$ref':f'#/$defs/{kind}'}).iter_errors(document)):
        raise ValueError(f'invalid_{kind}')


def validate_response(response, request=None):
    check(response,'response')
    c,items = response['completeness'],response['items']
    for key in ('served_at','observed_from','observed_until'):
        utc(response[key])
    start,end,served = (utc(response[k]) for k in ('observed_from','observed_until','served_at'))
    if not start<=end<=served or response['oldest_observation_age_s']!=(served-start).total_seconds():
        raise ValueError('response_time_mismatch')
    if any(type(c[k]) is not int for k in ('requested','returned','failed','unknown','out_of_scope')):
        raise ValueError('response_count_requires_literal_integer')
    if request is not None:
        check(request,'request')
        if response['request_id']!=request['request_id']:
            raise ValueError('response_request_identity_mismatch')
        if c['requested']!=len(request['items']):
            raise ValueError('response_request_count_mismatch')
        if response['status']!='refused':
            if any(response[k]!=request[k] for k in ('source','package_sha256','profile_ref','frame_id','mode','purpose')):
                raise ValueError('response_request_binding_mismatch')
            if [i['item_id'] for i in response['items']] != [i['item_id'] for i in request['items']]:
                raise ValueError('response_request_items_mismatch')
    if response['status']!='refused' and (response['mode']!='historical' or response['purpose']!='spatial_query'):
        raise ValueError('unsupported_success_mode')
    if response['status']!='refused':
        if not response['quality']['declared_limits_met'] or response['quality']['reasons']:
            raise ValueError('success_with_failed_quality')
        if response['max_age_s'] is not None and response['oldest_observation_age_s']>response['max_age_s']:
            raise ValueError('success_with_stale_observation')
        if request is not None and request['max_age_s'] is not None and (response['max_age_s'] is None or response['max_age_s']>request['max_age_s']):
            raise ValueError('response_loosened_freshness')
    ids = [i['item_id'] for i in items]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate_response_item')
    result = [i for i in items if i['status']=='result']
    failed = len(items)-len(result)
    if response['status']=='refused':
        if response['refusal'] is None or items or c != {**c,'returned':0,'failed':0,'unknown':0,'out_of_scope':0,'status':'none'}:
            raise ValueError('invalid_refusal_envelope')
    else:
        if (response['refusal'] is not None or len(items)!=c['requested'] or c['returned']!=len(result)
                or c['failed']!=failed or c['unknown']!=sum(i['state']=='unknown' for i in result)
                or c['out_of_scope']!=sum(i['state']=='out_of_scope' for i in result)
                or c['status']!=('partial' if failed else 'complete')
                or response['status']!=('partial' if failed else 'completed')):
            raise ValueError('response_completeness_mismatch')
    for item in result:
        reason = item['reason']
        expected = ('out_of_scope' if reason=='outside_target_scope' else
                    None if reason=='synthetic_observation' else 'unknown')
        if expected is not None and item['state']!=expected:
            raise ValueError('state_reason_mismatch')
        if reason=='synthetic_observation' and item['state'] not in ('occupied','observed_free'):
            raise ValueError('state_reason_mismatch')
    return True


class InspectionConsumer:
    def __init__(self, source_snapshot, voxel_files, *, now):
        source_snapshot = dict(source_snapshot)
        self._report = inspect_release_snapshot(source_snapshot,now=now)
        self._pin = pinned_voxel_source(source_snapshot,now=now)
        release = read_json(source_snapshot['release.json'])
        self._profile = read_json(source_snapshot[release['quality_profile']['path']])
        self._assessment = read_json(source_snapshot[release['quality_assessment']['path']])
        self._profile_ref = {k:release['quality_profile'][k] for k in ('id','sha256')}
        self._session = VoxelSession(voxel_files,self._pin)

    def consume(self, request, *, now):
        request = copy.deepcopy(request)
        check(request,'request')
        ids = [i['item_id'] for i in request['items']]
        if len(set(ids)) != len(ids):
            raise ValueError('duplicate_request_item')
        if request['max_age_s'] is not None and type(request['max_age_s']) is not int:
            raise ValueError('max_age_requires_literal_integer')
        current = utc(now)
        start,end = utc(self._assessment['observed_from']),utc(self._assessment['observed_until'])
        if current < end:
            raise ValueError('future_observation')
        limits = [v for v in (request['max_age_s'],self._profile['freshness']['max_age_s']) if v is not None]
        max_age = min(limits) if limits else None
        age = (current-start).total_seconds()
        quality = self._report['quality']
        # Separate the current per-request freshness calculation from F03 quality metrics.
        quality_reasons = [r for r in quality['reasons'] if r!='stale_observation']
        response = {
            'schema_version':'cospace.consumption/0.1','kind':'response','request_id':request['request_id'],
            'source':copy.deepcopy(self._pin['source']),'package_sha256':self._session.manifest_sha256,
            'profile_ref':copy.deepcopy(self._profile_ref),'served_at':now,
            'frame_id':self._pin['frame_id'],'mode':request['mode'],'purpose':request['purpose'],'usage':'historical_inspection_only',
            'observed_from':self._assessment['observed_from'],'observed_until':self._assessment['observed_until'],
            'valid_until':None,'max_age_s':max_age,'oldest_observation_age_s':age,
            'quality':{'grade_label':self._profile['rule']['grade_label'],'declared_limits_met':not quality_reasons,
                       'evidence_verified':False,'reasons':quality_reasons},
            'status':'refused','refusal':None,'completeness':{'requested':len(ids),'returned':0,'failed':0,'unknown':0,'out_of_scope':0,'status':'none'},
            'items':[],'authorized':False,'robot_ready':False}
        refusal = None
        if request['source']!=self._pin['source'] or request['package_sha256']!=self._session.manifest_sha256:
            refusal='source_mismatch'
        elif request['profile_ref']!=self._profile_ref:
            refusal='profile_mismatch'
        elif request['frame_id']!=self._pin['frame_id']:
            refusal='frame_mismatch'
        elif request['purpose']!='spatial_query' or self._profile['purpose']!='spatial_query':
            refusal='purpose_not_supported'
        elif request['mode']!=self._profile['mode']:
            refusal='mode_mismatch'
        elif request['mode']=='operational':
            refusal='runtime_authority_unavailable'
        elif max_age is not None and age>max_age:
            refusal='stale_observation'
        elif quality_reasons:
            refusal='quality_requirements_not_met'
        response['refusal']=refusal
        if refusal is None:
            for item in request['items']:
                point = item['point']
                if not isinstance(point,list) or len(point)!=3 or not all(finite_number(x) for x in point):
                    response['items'].append({'item_id':item['item_id'],'status':'error','error_code':'invalid_point'})
                    continue
                try:
                    result = self._session.query(point)
                except ValueError:
                    response['items'].append({'item_id':item['item_id'],'status':'error','error_code':'query_failed'})
                    continue
                response['items'].append({'item_id':item['item_id'],'status':'result','state':result['state'],'reason':result['reason']})
            items = response['items']
            results = [i for i in items if i['status']=='result']
            failed = len(items)-len(results)
            response['status']='partial' if failed else 'completed'
            response['completeness'].update(returned=len(results),failed=failed,
                unknown=sum(i['state']=='unknown' for i in results),out_of_scope=sum(i['state']=='out_of_scope' for i in results),
                status='partial' if failed else 'complete')
        validate_response(response,request)
        return response
