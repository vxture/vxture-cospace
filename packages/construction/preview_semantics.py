"""Create a semantic candidate over immutable geometry; no source re-estimation."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import uuid
import numpy as np
from packages.construction.preview_jobs import now
from packages.construction.preview_model import PreviewModel,digest
from packages.lifecycle.preview_scope import scope,match
from packages.ontology.preview_relations import inspect_relations
from packages.lifecycle.preview_control_lock import serialized


class ObjectRulesFailed(ValueError):
    def __init__(self,report):
        super().__init__('object_rules_failed');self.report=report


@serialized(lambda jobs:jobs.root.parent)
def annotate(jobs,ontologies,request,*,business=None,relations=None):
    ownership=scope(jobs.directory,request.space_id)
    base=jobs.model(request.base_candidate_id);match(base.manifest,ownership)
    jobs.controls.require_active(request.space_id,'candidate:'+request.base_candidate_id)
    if digest(base.root/'model.json')!=request.base_manifest_sha256:
        raise ValueError('base_candidate_integrity_changed')
    ref=request.ontology_ref.model_dump()
    drafts=[{k:getattr(obj,k) for k in ('object_id','type_id','properties')} for obj in request.objects]
    report=ontologies.inspect(ref['ontology_id'],ref['version'],ref['sha256'],drafts)
    if report['status']!='passed':raise ObjectRulesFailed(report)
    ontology_raw=(ontologies.path(ref['ontology_id'],ref['version'])/'definition.json').read_bytes()
    saved_relations=relations
    if saved_relations is None and getattr(base,'relation_snapshot',None) is not None:
        ids={o.object_id for o in request.objects}
        saved_relations=[r for r in base.relation_snapshot['relations'] if r['source_id'] in ids and r['target_id'] in ids]
    if saved_relations is not None:
        ontology=json.loads(ontology_raw)
        if not ontology.get('relations'):raise ValueError('ontology_relations_not_available')
        report=inspect_relations(ontology,drafts,saved_relations)
        if report['status']!='passed':raise ObjectRulesFailed(report)
    with np.load(base.root/'spatial.npz',allow_pickle=False) as arrays:points=arrays['points']
    objects=[]
    for draft in request.objects:
        if draft.point_index>=len(points):raise ValueError('object_point_index_out_of_range')
        objects.append({'object_id':draft.object_id,'type_id':draft.type_id,'properties':draft.properties,
                        'anchor_m':points[draft.point_index].astype(float).tolist(),
                        'confirmation':'unverified','evidence':{'kind':'model_point','member':'spatial.npz',
                            'sha256':base.manifest['members']['spatial.npz']['sha256'],'point_index':draft.point_index}})
    with jobs.lock:
        jobs.poll()
        if jobs.active:raise ValueError('build_already_running')
        if digest(base.root/'model.json')!=request.base_manifest_sha256:
            raise ValueError('base_candidate_integrity_changed')
        identity='build-'+uuid.uuid4().hex[:16];annotation_id='annotation-'+uuid.uuid4().hex[:16]
        staging=jobs.root/('.pending-'+identity);staging.mkdir();output=staging/'output';output.mkdir()
        try:
            manifest=deepcopy(base.manifest)
            for name in base.manifest['members']:
                if name in ('objects.json','ontology.json','business.json','relations.json'):continue
                if Path(name).name!=name:raise ValueError('invalid_member_name')
                shutil.copyfile(base.root/name,output/name)
            base_ref={'candidate_id':request.base_candidate_id,'model_manifest_sha256':request.base_manifest_sha256}
            doc={'profile':'cospace.preview-objects/0.1','model_id':identity,'annotation_id':annotation_id,
                 'created_at':now(),'frame_id':manifest['frame_id'],'unit':'m',**ownership,
                 'source_model_sha256':manifest['members']['spatial.npz']['sha256'],
                 'ontology_ref':ref,'base_candidate_ref':base_ref,'objects':objects}
            (output/'objects.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
            (output/'ontology.json').write_bytes(ontology_raw)
            manifest.update(id=identity,created_at=now())
            manifest['semantic_annotation']={'annotation_id':annotation_id,'object_count':len(objects),
                'objects_path':'objects.json','ontology_path':'ontology.json','ontology_ref':ref,
                'base_candidate_ref':base_ref,'confirmation':'unverified'}
            for view in ('human_view','agent_view'):
                manifest[view].update(objects_path='objects.json',ontology_ref=ref)
            manifest['quality']['semantic_annotation']='manual_model_point_annotation_unverified'
            manifest['limitations']=[x for x in manifest.get('limitations',[]) if x!='no_semantic_objects']
            if 'semantic_objects_unverified' not in manifest['limitations']:manifest['limitations'].append('semantic_objects_unverified')
            for name in ('objects.json','ontology.json'):
                path=output/name;manifest['members'][name]={'sha256':digest(path),'bytes':path.stat().st_size}
            manifest['members'].pop('business.json',None);manifest.pop('business_association',None)
            saved=business if business is not None else getattr(base,'business_snapshot',None)
            if saved is not None:
                ids={obj['object_id'] for obj in objects}
                bindings=[b for b in saved['bindings'] if b['object_id'] in ids]
                used={b['ledger_ref']['record_id'] for b in bindings}
                frozen={'profile':'cospace.preview-business/0.1','model_id':identity,**ownership,
                        'objects_sha256':manifest['members']['objects.json']['sha256'],
                        'bindings':bindings,'records':[r for r in saved['records'] if r['ref']['record_id'] in used],
                        'confirmation':'unverified'}
                (output/'business.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
                manifest['business_association']={'path':'business.json','binding_count':len(bindings)}
                path=output/'business.json';manifest['members']['business.json']={'sha256':digest(path),'bytes':path.stat().st_size}
            manifest['members'].pop('relations.json',None);manifest.pop('object_relations',None)
            if saved_relations is not None:
                frozen={'profile':'cospace.preview-relations/0.1','model_id':identity,**ownership,
                        'objects_sha256':manifest['members']['objects.json']['sha256'],'ontology_ref':ref,
                        'relations':saved_relations,'confirmation':'unverified'}
                (output/'relations.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
                path=output/'relations.json';manifest['members']['relations.json']={'sha256':digest(path),'bytes':path.stat().st_size}
                manifest['object_relations']={'path':'relations.json','relation_count':len(saved_relations)}
            (output/'model.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            shutil.copyfile('experiments/templates/nyu-flow-preview.html',output/'index.html')
            current=PreviewModel(output)
            cell=next(iter(current.cells));unknown=(max(c[0] for c in current.cells)+2,0,0)
            checks={'surface':current.query(((np.asarray(cell)+.5)*current.resolution).tolist()),
                    'unknown':current.query(((np.asarray(unknown)+.5)*current.resolution).tolist()),
                    'same_source_model':manifest['human_view']['source_model_sha256']==manifest['agent_view']['source_model_sha256'],
                    'semantic_objects':current.objects(),
                    'checks_scope':'saved_local_implementation_checks_not_field_verification'}
            (output/'offline-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
            base_job=json.loads((base.root.parent/'job.json').read_bytes())
            record={'id':identity,'state':'succeeded','created_at':now(),'finished_at':now(),**ownership,
                    'input_id':base_job['input_id'],'input_binding':base_job['input_binding'],
                    'method':'manual_semantic_annotation_over_fixed_geometry','stage':'semantic_candidate_and_dual_views',
                    'base_candidate_id':request.base_candidate_id,'base_manifest_sha256':request.base_manifest_sha256,
                    'annotation_id':annotation_id,'object_count':len(objects),
                    'candidate_url':f'/candidates/{identity}/','error':None}
            if base_job.get('batch_ref'):record['batch_ref']=base_job['batch_ref']
            if business is not None:
                record.update(method='manual_business_association_over_fixed_geometry',business_binding_count=len(bindings))
            if relations is not None:
                record.update(method='manual_object_relations_over_fixed_geometry',relation_count=len(saved_relations))
            (staging/'job.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            staging.rename(jobs.root/identity)
            return record
        finally:
            if staging.exists():
                for file in output.iterdir():file.unlink()
                output.rmdir()
                (staging/'job.json').unlink(missing_ok=True);staging.rmdir()
