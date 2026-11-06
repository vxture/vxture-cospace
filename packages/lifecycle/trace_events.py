"""F06c closed synthetic trace graph and idempotent in-memory event reception."""
import copy
import json
import re
import threading
from pathlib import Path

from jsonschema import Draft202012Validator

from packages.spatial.changes import canonical, digest
from packages.spatial.quality_contract import utc

SCHEMA=Path(__file__).resolve().parents[2]/'contracts/schemas/trace-events-v0.1.schema.json'
EVENT_KINDS={'cospace.candidate.created.v1':('candidate_build','candidate'),
             'cospace.candidate.inspected.v1':('candidate_inspection','inspection')}


def schema_check(document, event=False):
    schema=json.loads(SCHEMA.read_text(encoding='utf-8'))
    if event:
        schema={'$defs':schema['$defs'],'$ref':'#/$defs/event'}
    if list(Draft202012Validator(schema).iter_errors(document)):
        raise ValueError('trace_structure')


def event_key(event):
    return event['source'],event['id']


def validate_trace(bundle, resources):
    bundle=copy.deepcopy(bundle)
    resources=dict(resources)
    schema_check(bundle)
    if len(resources)>128 or any(type(raw) is not bytes or len(raw)>8388608 for raw in resources.values()) or sum(map(len,resources.values()))>33554432:
        raise ValueError('trace_resource_budget')
    folded=set()
    for path in resources:
        if (not isinstance(path,str) or not path or '\\' in path or re.search(r'[<>:"|?*\x00-\x1f]',path)
                or any(p in ('','.','..') or p.endswith((' ','.'))
                       or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',p.split('.')[0])
                       for p in path.split('/'))):
            raise ValueError('unsafe_trace_path')
        if path.casefold() in folded:
            raise ValueError('trace_path_collision')
        folded.add(path.casefold())
    ids=set()
    def index(items):
        result={}
        for item in items:
            if item['id'] in ids:
                raise ValueError('duplicate_trace_identity')
            ids.add(item['id'])
            result[item['id']]=item
        return result
    agents=index(bundle['agents'])
    entities=index(bundle['entities'])
    activities=index(bundle['activities'])
    used_paths=set()
    for entity in entities.values():
        ref=entity['member']
        raw=resources.get(ref['path'])
        if raw is None:
            raise ValueError('missing_trace_resource')
        if ref['path'] in used_paths:
            raise ValueError('duplicate_trace_resource')
        used_paths.add(ref['path'])
        if type(ref['bytes']) is not int or len(raw)!=ref['bytes'] or digest(raw)!=ref['sha256']:
            raise ValueError('trace_resource_integrity')
    if used_paths!=set(resources):
        raise ValueError('unreferenced_trace_resource')
    generated={}
    times={}
    for activity in activities.values():
        if activity['agent_id'] not in agents:
            raise ValueError('unknown_trace_agent')
        start,end=utc(activity['started_at']),utc(activity['ended_at'])
        if end<start:
            raise ValueError('reversed_activity_time')
        times[activity['id']]=(start,end)
        if set(activity['used'])&set(activity['generated']):
            raise ValueError('activity_uses_own_output')
        if (set(activity['used'])|set(activity['generated']))-entities.keys():
            raise ValueError('unknown_trace_entity')
        for identity in activity['generated']:
            if identity in generated:
                raise ValueError('multiple_entity_generators')
            generated[identity]=activity['id']
    graph={identity:set() for identity in activities}
    for activity in activities.values():
        for identity in activity['used']:
            parent=generated.get(identity)
            if parent is not None:
                graph[activity['id']].add(parent)
                if times[parent][1]>times[activity['id']][0]:
                    raise ValueError('entity_used_before_generation')
    def acyclic(graph):
        visited,active=set(),set()
        def visit(identity):
            if identity in active:
                raise ValueError('trace_cycle')
            if identity in visited:
                return
            active.add(identity)
            for parent in graph[identity]:
                visit(parent)
            active.remove(identity)
            visited.add(identity)
        for identity in graph:
            visit(identity)
    acyclic(graph)
    events={}
    correlations=set()
    activity_events=set()
    for event in bundle['events']:
        key=event_key(event)
        if key in events:
            raise ValueError('duplicate_event_in_archive')
        events[key]=event
        data=event['data']
        if data['trace_id']!=bundle['trace_id'] or data['scene_id']!=bundle['scene_id']:
            raise ValueError('event_trace_binding_mismatch')
        correlations.add(data['correlation_id'])
        activity=activities.get(data['activity_id'])
        entity=entities.get(data['entity_id'])
        activity_kind,entity_kind=EVENT_KINDS[event['type']]
        if (activity is None or entity is None or activity['kind']!=activity_kind or entity['kind']!=entity_kind
                or entity['id'] not in activity['generated'] or event['subject']!=entity['id']):
            raise ValueError('event_activity_entity_mismatch')
        if utc(event['time'])!=times[activity['id']][1]:
            raise ValueError('event_activity_time_mismatch')
        if activity['id'] in activity_events:
            raise ValueError('multiple_events_for_activity')
        activity_events.add(activity['id'])
    if len(correlations)!=1 or activity_events!=set(activities):
        raise ValueError('incomplete_event_activity_coverage')
    causal_graph={key:set() for key in events}
    for key,event in events.items():
        cause=event['data']['causation']
        if cause is None:
            if graph[event['data']['activity_id']]:
                raise ValueError('missing_causal_event')
            continue
        parent_key=(cause['source'],cause['id'])
        if parent_key not in events:
            raise ValueError('missing_causal_event')
        parent=events[parent_key]
        if parent['data']['activity_id'] not in graph[event['data']['activity_id']]:
            raise ValueError('causal_event_not_input_dependency')
        if utc(parent['time'])>utc(event['time']):
            raise ValueError('reversed_causal_time')
        causal_graph[key].add(parent_key)
    acyclic(causal_graph)
    return {'trace_id':bundle['trace_id'],'entities':len(entities),'activities':len(activities),
            'events':len(events),'content_integrity_verified':True,
            'actor_identity_verified':False,'evidence_semantics_verified':False,
            'authorized':False,'robot_ready':False}


class EventInbox:
    """Source+ID idempotency only; accepting an envelope does not apply its business effect."""
    def __init__(self):
        self._events={}
        self._lock=threading.Lock()

    def receive(self,event):
        event=copy.deepcopy(event)
        schema_check(event,event=True)
        utc(event['time'])
        key=event_key(event)
        sha=digest(canonical(event))
        with self._lock:
            existing=self._events.get(key)
            if existing is not None:
                if existing[0]!=sha:
                    raise ValueError('event_identity_content_conflict')
                return {'accepted':False,'duplicate':True,'business_applied':False}
            if len(self._events)>=256:
                raise ValueError('inbox_budget')
            self._events[key]=(sha,event)
            return {'accepted':True,'duplicate':False,'business_applied':False}

    def snapshot(self):
        with self._lock:
            return copy.deepcopy([record[1] for record in self._events.values()])


def export_prov(bundle, resources):
    """Small JSON-LD PROV mapping, not a complete PROV-O reasoner or conformance proof."""
    validate_trace(bundle,resources)
    prefix=f"urn:cospace:trace:{bundle['trace_id']}:"
    nodes=[]
    for agent in bundle['agents']:
        nodes.append({'@id':prefix+agent['id'],'@type':'prov:Agent','rdfs:label':agent['label']})
    for entity in bundle['entities']:
        nodes.append({'@id':prefix+entity['id'],'@type':'prov:Entity','cospace:sha256':entity['member']['sha256']})
    for activity in bundle['activities']:
        node={'@id':prefix+activity['id'],'@type':'prov:Activity',
              'prov:used':[{'@id':prefix+i} for i in activity['used']],
              'prov:wasAssociatedWith':{'@id':prefix+activity['agent_id']},
              'prov:startedAtTime':{'@value':activity['started_at'],'@type':'xsd:dateTime'},
              'prov:endedAtTime':{'@value':activity['ended_at'],'@type':'xsd:dateTime'}}
        nodes.append(node)
        for identity in activity['generated']:
            nodes.append({'@id':prefix+identity,'prov:wasGeneratedBy':{'@id':prefix+activity['id']},
                          'prov:wasDerivedFrom':[{'@id':prefix+i} for i in activity['used']]})
    return {'@context':{'prov':'http://www.w3.org/ns/prov#','rdfs':'http://www.w3.org/2000/01/rdf-schema#',
                        'xsd':'http://www.w3.org/2001/XMLSchema#','cospace':'urn:cospace:vocab:'},'@graph':nodes}
