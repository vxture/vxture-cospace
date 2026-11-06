"""Deterministic F04 synthetic fixture with real byte digests, no measured geometry."""
import copy
import hashlib
import json
from pathlib import Path

VERSION = 'cospace.spatial-release/0.1'


def build_release_sample(patches=None):
    patches = patches or {}
    files = {}
    def store(path, identity, doc):
        doc = copy.deepcopy(doc)
        if path in patches:
            patches[path](doc)
        raw = json.dumps(doc, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        files[path] = raw
        return {'id':identity, 'path':path, 'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)}
    def doc(kind, identity, **extra):
        return {'schema_version':VERSION, 'kind':kind, 'id':identity, **extra}
    def compact(ref):
        return {k:ref[k] for k in ('id','sha256')}

    frame = store('frame.json','scene',doc('frame','scene',unit='m',handedness='right',axes=['corridor','left','up'],origin='synthetic entrance'))
    scope = store('scope.json','target-v1',doc('scope','target-v1',frame_id='scene',bounds=[[0,0,0],[10,10,1]],cell_size_m=1))
    ontology = store('ontology.json','ontology-v1',doc('ontology','ontology-v1',version='0.1',type_ids=['Cabinet']))
    objects = store('objects.json','objects-v1',doc('objects','objects-v1',frame_id='scene',ontology=ontology,instances=[
        {'object_id':'cabinet-a','type_id':'Cabinet','anchor':[2,2,0]},
        {'object_id':'cabinet-b','type_id':'Cabinet','anchor':[5,2,0]}]))
    geometry = store('geometry.json','geometry-v1',{'notice':'synthetic placeholder, not a decoded geometric format'})
    coverage = store('coverage.json','partition-v1',{'notice':'synthetic partition placeholder, aggregate counts not derived from cells'})
    procedure = store('procedure.json','test-procedure',{'notice':'synthetic test thresholds only, no approved grade'})
    check = store('check-points.json','check-set',{'notice':'synthetic placeholder, no independent survey'})
    provenance = store('provenance.json','provenance-v1',{'resources':[procedure,check]})
    truth = store('truth.json','truth-v1',doc('truth','truth-v1',scene_id='synthetic-equipment-corridor',data_kind='synthetic',
        frame=frame,scope=scope,ontology=ontology,objects=objects,geometry=geometry,coverage=coverage,provenance=provenance))
    quality_path = Path(__file__).resolve().parents[2] / 'examples/quality-profile/equipment-synthetic.json'
    base = json.loads(quality_path.read_text(encoding='utf-8'))
    expected_scope = {'scope_ref':compact(scope),'frame_id':'scene','bounds':[[0,0,0],[10,10,1]],'cell_size_m':1}
    profile, assessment = base['profile'], base['assessment']
    profile.update(scope=expected_scope)
    profile['rule'].update(procedure_ref=compact(procedure),target_objects_ref=compact(objects),expected_object_count=2)
    assessment.update(scope=expected_scope,truth_ref=compact(truth),procedure_ref=compact(procedure))
    assessment['coverage']['partition_ref'] = compact(coverage)
    assessment['semantics'].update(target_objects_ref=compact(objects),required_count=2,confirmed_count=2)
    assessment['geometry']['check_points_ref'] = compact(check)
    profile_ref = store('profile.json',profile['profile_id'],profile)
    quality_ref = store('assessment.json',assessment['assessment_id'],assessment)
    views = []
    for kind in ('human','machine'):
        artifact = store(f'{kind}-payload.json',f'{kind}-payload',{'notice':f'synthetic {kind} placeholder; no GLB, voxel or localization data'})
        derivation = store(f'{kind}-derivation.json',f'{kind}-derivation',{'implementation':'synthetic-fixture/0.1','config':'no algorithm executed'})
        views.append(store(f'{kind}.json',f'{kind}-v1',doc('view',f'{kind}-v1',scene_id='synthetic-equipment-corridor',data_kind='synthetic',
            view_kind=kind,source_truth=truth,frame=frame,scope=scope,ontology=ontology,quality=quality_ref,
            derivation=derivation,artifacts=[artifact],object_ids=['cabinet-a','cabinet-b'],expression={
                'encoding':'synthetic-placeholder-json/0.1','intended_use':'synthetic_inspection',
                'losses':['not_measured_geometry','no_runtime_capability'], 'max_geometric_error_m':None,'validation':'not_field_validated'})))
    store('release.json','release-v1',doc('release','release-v1',scene_id='synthetic-equipment-corridor',data_kind='synthetic',
        source_truth=truth,quality_profile=profile_ref,quality_assessment=quality_ref,views=views,adoption='sample_only'))
    return files
