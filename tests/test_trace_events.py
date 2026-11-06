import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from packages.lifecycle.trace_events import SCHEMA, EventInbox, export_prov, validate_trace
from packages.lifecycle.trace_sample import build_trace_sample, trace_sample_files


@pytest.fixture
def sample():
    return build_trace_sample()


def test_schema():
    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text(encoding='utf-8')))


def test_complete_sample_preserves_inputs_and_authority_boundary(sample):
    original = copy.deepcopy(sample)
    report = validate_trace(*sample)
    assert report['content_integrity_verified'] and report['activities']==2
    assert not any(report[k] for k in ('authorized','robot_ready','actor_identity_verified','evidence_semantics_verified'))
    assert sample == original
    sample[0]['events'].reverse()
    assert validate_trace(*sample)==report


@pytest.mark.parametrize('mode,message',[
    ('tamper','trace_resource_integrity'),('missing','missing_trace_resource'),
    ('extra','unreferenced_trace_resource'),('collision','trace_path_collision'),
    ('unsafe','unsafe_trace_path'),('wrong_type','trace_resource_budget')])
def test_resource_failures(sample,mode,message):
    resources=sample[1]
    path=next(iter(resources))
    if mode=='tamper': resources[path]+=b'x'
    if mode=='missing': del resources[path]
    if mode=='extra': resources['extra.txt']=b'x'
    if mode=='collision': resources[path.upper()]=resources[path]
    if mode=='unsafe': resources['../escape']=b'x'
    if mode=='wrong_type': resources[path]='text'
    with pytest.raises(ValueError,match=message): validate_trace(*sample)


@pytest.mark.parametrize('case,message',[
    ('agent','unknown_trace_agent'),('entity','unknown_trace_entity'),
    ('duplicate','duplicate_trace_identity'),('generator','multiple_entity_generators'),
    ('own_output','activity_uses_own_output'),('reversed','reversed_activity_time'),
    ('early_use','entity_used_before_generation'),('event_time','event_activity_time_mismatch'),
    ('cause','missing_causal_event'),('missing_cause','missing_causal_event'),
    ('wrong_cause','causal_event_not_input_dependency'),
    ('trace','event_trace_binding_mismatch'),('scene','event_trace_binding_mismatch'),
    ('correlation','incomplete_event_activity_coverage'),('subject','event_activity_entity_mismatch'),
    ('type','event_activity_entity_mismatch'),('duplicate_event','duplicate_event_in_archive'),
    ('missing_event','incomplete_event_activity_coverage'),('duplicate_activity_event','multiple_events_for_activity')])
def test_graph_failures(sample,case,message):
    bundle=sample[0]
    first,second=bundle['activities']
    e1,e2=bundle['events']
    if case=='agent': first['agent_id']='missing'
    if case=='entity': first['used'].append('missing')
    if case=='duplicate': bundle['agents'][1]['id']=bundle['agents'][0]['id']
    if case=='generator': second['used'].remove(first['generated'][0]); second['generated'].append(first['generated'][0])
    if case=='own_output': first['used'].append(first['generated'][0])
    if case=='reversed': first['started_at']='2026-10-28T02:00:00Z'
    if case=='early_use': second['started_at']='2026-10-28T00:00:00Z'
    if case=='event_time': e2['time']='2026-10-28T01:00:03Z'
    if case=='cause': e2['data']['causation']['id']='missing'
    if case=='missing_cause': e2['data']['causation']=None
    if case=='wrong_cause': e1['data']['causation']={'source':e2['source'],'id':e2['id']}
    if case=='trace': e1['data']['trace_id']='other'
    if case=='scene': e1['data']['scene_id']='other'
    if case=='correlation': e2['data']['correlation_id']='other'
    if case=='subject': e1['subject']='missing'
    if case=='type': e1['type']=e2['type']
    if case=='duplicate_event': bundle['events'].append(copy.deepcopy(e1))
    if case=='missing_event': bundle['events'].pop()
    if case=='duplicate_activity_event':
        extra=copy.deepcopy(e1); extra['id']='extra'; bundle['events'].append(extra)
    with pytest.raises(ValueError,match=message): validate_trace(*sample)


def test_cycle_rejected_even_with_equal_timestamps(sample):
    bundle=sample[0]
    for activity in bundle['activities']:
        activity['started_at']=activity['ended_at']='2026-10-28T01:00:00Z'
    bundle['activities'][0]['used'].append(bundle['activities'][1]['generated'][0])
    with pytest.raises(ValueError,match='trace_cycle'): validate_trace(*sample)


@pytest.mark.parametrize('path',['/absolute','C:/drive','a\\b','a//b','a/CON.txt','a/file?.json'])
def test_nonportable_resource_paths_rejected(sample,path):
    sample[1][path]=b'x'
    with pytest.raises(ValueError,match='unsafe_trace_path'): validate_trace(*sample)


@pytest.mark.parametrize('field,value',[('authorized',True),('robot_ready',True),('unexpected',False)])
def test_authority_and_unknown_fields_rejected(sample,field,value):
    sample[0]['events'][0]['data'][field]=value
    with pytest.raises(ValueError,match='trace_structure'): validate_trace(*sample)


def test_published_event_unsupported(sample):
    sample[0]['events'][0]['type']='cospace.release.published.v1'
    with pytest.raises(ValueError,match='trace_structure'): validate_trace(*sample)


@pytest.mark.parametrize('stamp',['2026-10-28T01:00:00+08:00','invalid','2026-02-30T01:00:00Z'])
def test_strict_utc(sample,stamp):
    sample[0]['events'][0]['time']=stamp
    with pytest.raises(ValueError): validate_trace(*sample)


def test_inbox_out_of_order_duplicate_and_mutation_isolation(sample):
    inbox=EventInbox()
    first,second=sample[0]['events']
    assert inbox.receive(second)=={'accepted':True,'duplicate':False,'business_applied':False}
    assert inbox.receive(first)['accepted']
    reordered=json.loads(json.dumps(first,sort_keys=True))
    assert inbox.receive(reordered)=={'accepted':False,'duplicate':True,'business_applied':False}
    first['subject']='mutated'
    assert inbox.snapshot()[1]['subject']!='mutated'
    snapshot=inbox.snapshot(); snapshot.clear()
    assert len(inbox.snapshot())==2


def test_conflicting_id_fails_but_distinct_source_is_distinct(sample):
    inbox=EventInbox(); event=sample[0]['events'][0]
    inbox.receive(event)
    changed=copy.deepcopy(event); changed['data']['correlation_id']='other'
    with pytest.raises(ValueError,match='event_identity_content_conflict'): inbox.receive(changed)
    changed['source']='urn:cospace:other'
    assert inbox.receive(changed)['accepted']


def test_inbox_is_staging_not_reference_validation(sample):
    inbox=EventInbox(); event=sample[0]['events'][1]
    event['data']['causation']['id']='absent'
    assert inbox.receive(event)['business_applied'] is False
    with pytest.raises(ValueError,match='missing_causal_event'): validate_trace(*sample)


def test_concurrent_delivery_one_acceptance(sample):
    inbox=EventInbox(); event=sample[0]['events'][0]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(inbox.receive,[event]*16))
    assert sum(r['accepted'] for r in results)==1
    assert sum(r['duplicate'] for r in results)==15
    assert all(r['business_applied'] is False for r in results)


def test_inbox_budget(sample):
    inbox=EventInbox(); event=sample[0]['events'][0]
    for i in range(256):
        event['id']=f'event-{i}'; inbox.receive(event)
    assert inbox.receive(event)['duplicate']
    event['id']='over-limit'
    with pytest.raises(ValueError,match='inbox_budget'): inbox.receive(event)


def test_prov_links_resolve_and_input_mutations_are_rejected(sample):
    prov=export_prov(*sample)
    ids={node['@id'] for node in prov['@graph']}
    for node in prov['@graph']:
        for key in ('prov:used','prov:wasAssociatedWith','prov:wasGeneratedBy','prov:wasDerivedFrom'):
            refs=node.get(key,[])
            if isinstance(refs,dict): refs=[refs]
            assert all(ref['@id'] in ids for ref in refs)
    assert sum('prov:wasGeneratedBy' in node for node in prov['@graph'])==5
    sample[1]['inspection/report.json']+=b'changed'
    with pytest.raises(ValueError,match='trace_resource_integrity'): export_prov(*sample)


def test_checked_in_sample_is_reproducible():
    files=trace_sample_files(); root=Path('examples/trace-events')
    assert {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}==set(files)
    for name,raw in files.items(): assert (root/name).read_bytes()==raw
