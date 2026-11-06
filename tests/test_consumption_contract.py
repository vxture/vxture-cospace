import copy
import json

import pytest
from jsonschema import Draft202012Validator

from packages.service.consumption_contract import InspectionConsumer, SCHEMA, validate_response
from packages.service.consumption_sample import build_consumption_sample

NOW='2026-10-28T00:30:00Z'


@pytest.fixture
def fixture():
    source,files,request=build_consumption_sample()
    return InspectionConsumer(source,files,now=NOW),request


def test_schema():
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text()))


def test_partial_batch_separates_unknown_outside_and_error(fixture):
    consumer,request=fixture
    r=consumer.consume(request,now=NOW)
    assert r['status']=='partial'
    assert r['completeness']=={'requested':5,'returned':4,'failed':1,'unknown':2,'out_of_scope':1,'status':'partial'}
    assert r['items'][-1]=={'item_id':'bad-point','status':'error','error_code':'invalid_point'}
    assert not r['authorized'] and not r['robot_ready'] and r['valid_until'] is None
    assert validate_response(r,request)


def test_all_unknown_still_complete_transport(fixture):
    consumer,request=fixture
    request['items']=request['items'][1:3]
    r=consumer.consume(request,now=NOW)
    assert r['status']=='completed' and r['completeness']['status']=='complete'
    assert r['completeness']['unknown']==2


def test_operational_refused_without_any_point_queries(monkeypatch):
    source,files,request=build_consumption_sample('operational')
    consumer=InspectionConsumer(source,files,now=NOW)
    monkeypatch.setattr(consumer._session,'query',lambda p:pytest.fail('must not query'))
    r=consumer.consume(request,now=NOW)
    assert r['refusal']=='runtime_authority_unavailable'
    assert r['items']==[] and r['completeness']['status']=='none'


def test_history_cannot_select_operational_profile():
    source,files,request=build_consumption_sample('operational')
    request['mode']='historical'
    r=InspectionConsumer(source,files,now=NOW).consume(request,now=NOW)
    assert r['refusal']=='mode_mismatch'


@pytest.mark.parametrize('key,value,reason', [
    ('package_sha256','1'*64,'source_mismatch'),('frame_id','other','frame_mismatch'),
    ('purpose','localize','purpose_not_supported'),('purpose','measure','purpose_not_supported'),
    ('mode','operational','mode_mismatch')])
def test_whole_request_refusals(fixture,key,value,reason):
    consumer,request=fixture
    request[key]=value
    r=consumer.consume(request,now=NOW)
    assert r['status']=='refused' and r['refusal']==reason and not r['items']


def test_profile_digest_mismatch(fixture):
    consumer,request=fixture
    request['profile_ref']['sha256']='1'*64
    assert consumer.consume(request,now=NOW)['refusal']=='profile_mismatch'


def test_truth_identity_mismatch(fixture):
    consumer,request=fixture
    request['source']['truth_id']='other'
    assert consumer.consume(request,now=NOW)['refusal']=='source_mismatch'


@pytest.mark.parametrize('age,refusal', [(1800,None),(1799,'stale_observation')])
def test_request_can_require_stricter_age(fixture,age,refusal):
    consumer,request=fixture
    request['max_age_s']=age
    assert consumer.consume(request,now=NOW)['refusal']==refusal


def test_explicit_history_can_read_old_snapshot(fixture):
    consumer,request=fixture
    r=consumer.consume(request,now='2026-11-01T00:00:00Z')
    assert r['status']=='partial' and r['max_age_s'] is None


def test_profile_limit_cannot_be_loosened_by_request():
    # Pin a historical profile with a finite limit, then request a longer age.
    from packages.service.release_sample import build_release_sample
    from packages.views.agent.voxel_sample import build_voxel_sample
    source=build_release_sample({'profile.json':lambda d:d.update(mode='historical')})
    files,pin=build_voxel_sample(source)
    _,_,request=build_consumption_sample()
    release=json.loads(source['release.json'])
    import hashlib
    request.update(source=pin['source'],package_sha256=hashlib.sha256(files['agent-voxel.json']).hexdigest(),
                   profile_ref={k:release['quality_profile'][k] for k in ('id','sha256')},max_age_s=7200)
    r=InspectionConsumer(source,files,now=NOW).consume(request,now='2026-10-28T01:00:01Z')
    assert r['max_age_s']==3600 and r['refusal']=='stale_observation'


def test_point_failure_is_not_unknown(fixture,monkeypatch):
    consumer,request=fixture
    request['items']=request['items'][:1]
    def fail(point):
        raise ValueError('simulated reader failure')
    monkeypatch.setattr(consumer._session,'query',fail)
    r=consumer.consume(request,now=NOW)
    assert r['items'][0]['error_code']=='query_failed'
    assert r['completeness']['unknown']==0


@pytest.mark.parametrize('point',[None,[],True,[float('nan'),0,0],[10**1000,0,0]])
def test_invalid_item_point_stays_local(fixture,point):
    consumer,request=fixture
    request['items'][0]['point']=point
    assert consumer.consume(request,now=NOW)['items'][0]['error_code']=='invalid_point'


def test_duplicate_item_ids_reject_batch(fixture):
    consumer,request=fixture
    request['items'][1]['item_id']=request['items'][0]['item_id']
    with pytest.raises(ValueError,match='duplicate_request_item'):
        consumer.consume(request,now=NOW)


@pytest.mark.parametrize('key,value', [('schema_version','cospace.consumption/9'),('items',[]),('max_age_s',-1)])
def test_invalid_envelope(fixture,key,value):
    consumer,request=fixture
    request[key]=value
    with pytest.raises(ValueError,match='invalid_request'):
        consumer.consume(request,now=NOW)


def test_response_counter_corruption_detected(fixture):
    consumer,request=fixture
    r=consumer.consume(request,now=NOW)
    r['completeness']['unknown']=0
    with pytest.raises(ValueError,match='completeness_mismatch'):
        validate_response(r,request)


def test_response_binding_corruption_detected(fixture):
    consumer,request=fixture
    r=consumer.consume(request,now=NOW)
    r['source']['release_sha256']='1'*64
    with pytest.raises(ValueError,match='request_binding_mismatch'):
        validate_response(r,request)


def test_no_mutation_between_queries(fixture):
    consumer,request=fixture
    before=copy.deepcopy(request)
    r=consumer.consume(request,now=NOW)
    r['source']['truth_id']='changed'
    assert request==before
    assert consumer.consume(request,now=NOW)['source']['truth_id']!='changed'


def test_quality_failure_is_whole_request_refusal():
    from packages.service.release_sample import build_release_sample
    from packages.views.agent.voxel_sample import build_voxel_sample
    import hashlib
    def profile(d):
        d.update(mode='historical')
        d['freshness']['max_age_s']=None
        d['rule']['max_error_m']=None
    source=build_release_sample({'profile.json':profile})
    files,pin=build_voxel_sample(source)
    _,_,request=build_consumption_sample()
    release=json.loads(source['release.json'])
    request.update(source=pin['source'],package_sha256=hashlib.sha256(files['agent-voxel.json']).hexdigest(),
                   profile_ref={k:release['quality_profile'][k] for k in ('id','sha256')})
    r=InspectionConsumer(source,files,now=NOW).consume(request,now=NOW)
    assert r['refusal']=='quality_requirements_not_met' and r['items']==[]


@pytest.mark.parametrize('change,message', [
    (lambda r:r.update(max_age_s=1),'success_with_stale'),
    (lambda r:r['quality'].update(declared_limits_met=False),'success_with_failed_quality'),
    (lambda r:r['items'][1].update(state='observed_free'),'state_reason_mismatch'),
    (lambda r:r.update(oldest_observation_age_s=0),'response_time_mismatch')])
def test_semantically_invalid_success_rejected(fixture,change,message):
    consumer,request=fixture
    # Use one known result and one conflict: preserve counts for state/reason test.
    request['items']=request['items'][:2]
    r=consumer.consume(request,now=NOW)
    change(r)
    if message=='state_reason_mismatch':
        r['completeness']['unknown']=0
    with pytest.raises(ValueError,match=message):
        validate_response(r,request)


def test_request_cannot_silently_drop_profile_or_freshness(fixture):
    consumer,request=fixture
    del request['profile_ref']
    with pytest.raises(ValueError,match='invalid_request'):
        consumer.consume(request,now=NOW)


def test_batch_budget(fixture):
    consumer,request=fixture
    request['items']=[{'item_id':str(i),'point':[0,0,0]} for i in range(257)]
    with pytest.raises(ValueError,match='invalid_request'):
        consumer.consume(request,now=NOW)


def test_example_requests_responses_reproducible():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'examples/consumption'
    for mode in ('historical','operational'):
        source,files,request=build_consumption_sample(mode)
        response=InspectionConsumer(source,files,now=NOW).consume(request,now=NOW)
        assert json.loads((root/f'{mode}-request.json').read_text(encoding='utf-8'))==request
        assert json.loads((root/f'{mode}-response.json').read_text(encoding='utf-8'))==response
