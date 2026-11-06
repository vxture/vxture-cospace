"""Reproducible synthetic trace over the actual F06b2 candidate builder."""
from packages.spatial.changes import canonical, digest
from packages.views.agent.voxel_change_sample import build_voxel_change_sample
from packages.views.agent.voxel_changes import build_voxel_candidate, VoxelCandidatePreview
from packages.lifecycle.trace_events import validate_trace, export_prov


def build_trace_sample():
    sample = build_voxel_change_sample()
    result = build_voxel_candidate(*sample)
    preview = VoxelCandidatePreview(*sample, result)
    resources = {'source/agent-voxel.json': sample[0]['agent-voxel.json'],
                 'source/pin.json': canonical(sample[1]),
                 'change/change.json': canonical(sample[2])}
    resources.update({'source/'+p: raw for p, raw in sample[0].items() if p != 'agent-voxel.json'})
    resources.update({'change/'+p: raw for p, raw in sample[3].items()})
    resources.update({'candidate/'+p: raw for p, raw in result['files'].items()})
    inspection = {'schema_version': 'cospace.synthetic-inspection/0.1',
                  'candidate_manifest_sha256': result['candidate_manifest_sha256'],
                  'rebuild_verified': True, 'independent_quality_verified': False,
                  'queries': [preview.query(p) for p in ([5.5,5.5,.5], [.5,.5,.5], [5.5,.5,.5])],
                  'authorized': False, 'robot_ready': False}
    resources['inspection/report.json'] = canonical(inspection)
    entities = []
    for n, (path, raw) in enumerate(sorted(resources.items())):
        kind = ('candidate' if path.startswith('candidate/') else
                'inspection' if path.startswith('inspection/') else
                'evidence' if path.endswith('change.txt') else
                'change' if path.startswith('change/') else 'source_snapshot')
        entities.append({'id': f'entity-{n:02}', 'kind': kind,
                         'member': {'path': path, 'bytes': len(raw), 'sha256': digest(raw)}})
    roots = [e['id'] for e in entities if e['kind'] not in ('candidate', 'inspection')]
    candidates = [e['id'] for e in entities if e['kind'] == 'candidate']
    manifest = next(e['id'] for e in entities if e['member']['path']=='candidate/agent-voxel-candidate.json')
    inspected = next(e['id'] for e in entities if e['kind']=='inspection')
    activities = [
        {'id':'build-001','kind':'candidate_build','agent_id':'builder',
         'started_at':'2026-10-28T01:00:00Z','ended_at':'2026-10-28T01:00:01Z',
         'used':roots,'generated':candidates},
        {'id':'inspect-001','kind':'candidate_inspection','agent_id':'inspector',
         'started_at':'2026-10-28T01:00:01Z','ended_at':'2026-10-28T01:00:02Z',
         'used':roots+candidates,'generated':[inspected]}]
    def event(identity, activity, entity, kind, cause):
        return {'specversion':'1.0','id':identity,'source':'urn:cospace:synthetic:trace',
                'type':kind,'subject':entity,'time':activity['ended_at'],
                'datacontenttype':'application/json',
                'data':{'schema_version':'cospace.trace-event-data/0.1','trace_id':'trace-001',
                        'scene_id':sample[1]['source']['scene_id'],'data_kind':'synthetic',
                        'activity_id':activity['id'],'entity_id':entity,'correlation_id':'run-001',
                        'causation':cause,'authorized':False,'robot_ready':False}}
    events = [event('created-001',activities[0],manifest,'cospace.candidate.created.v1',None),
              event('inspected-001',activities[1],inspected,'cospace.candidate.inspected.v1',
                    {'source':'urn:cospace:synthetic:trace','id':'created-001'})]
    bundle = {'schema_version':'cospace.trace-events/0.1','trace_id':'trace-001',
              'scene_id':sample[1]['source']['scene_id'],'data_kind':'synthetic',
              'agents':[{'id':'builder','kind':'software','label':'Synthetic candidate builder'},
                        {'id':'inspector','kind':'software','label':'Synthetic rebuild inspector'}],
              'entities':entities,'activities':activities,'events':events}
    return bundle, resources


def trace_sample_files():
    bundle, resources = build_trace_sample()
    return {'trace.json':canonical(bundle), 'prov.jsonld':canonical(export_prov(bundle,resources)),
            'validation.json':canonical(validate_trace(bundle,resources)),
            **{'resources/'+p:raw for p,raw in resources.items()}}
