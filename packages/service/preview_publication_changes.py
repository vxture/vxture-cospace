"""Read-only changes and saved review provenance between two fixed publications."""
import re
from pydantic import BaseModel,ConfigDict,Field
from packages.construction.preview_changes import compare_models,checksum
from packages.construction.preview_model import digest
from packages.lifecycle.preview_scope import scope,match


class PublicationCompareRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    space_id:str|None=Field(default=None,min_length=1,max_length=100)
    base_publication_id:str=Field(pattern=r'^preview-[a-f0-9]{16}$')
    target_publication_id:str=Field(pattern=r'^preview-[a-f0-9]{16}$')


def read_fixed(publications,identity,ownership):
    if not re.fullmatch(r'preview-[a-f0-9]{16}',identity):
        raise ValueError('publication_not_found')
    record_path=publications.root/identity/'publication.json'
    before=digest(record_path)
    record,model=publications.read(identity)
    match(record,ownership);match(model.manifest,ownership)
    if (record.get('id')!=identity or record.get('candidate_id')!=model.manifest['id']
            or record.get('model_manifest_sha256')!=digest(model.root/'model.json')
            or record.get('source_model_sha256')!=model.manifest['members']['spatial.npz']['sha256']):
        raise ValueError('publication_snapshot_binding_mismatch')
    ref=publication_ref(record,model)
    if before!=ref['publication_record_sha256']:
        raise ValueError('publication_record_changed')
    return record,model,ref


def publication_ref(record,model):
    return {'publication_id':record['id'],'candidate_id':record['candidate_id'],
            'model_manifest_sha256':record['model_manifest_sha256'],
            'publication_record_sha256':digest(model.root/'publication.json'),
            'created_at':record['created_at']}


def review_provenance(record,requested_base):
    review=record.get('selection_review')
    if review is None:
        return {'status':'not_recorded','matches_requested_base_model':None,'saved_review':None}
    valid=False;matches=None
    try:
        comparison=review['comparison']
        base_ref=comparison['base_ref']
        base_ref_valid=(base_ref is None or (
            isinstance(base_ref,dict) and set(base_ref)=={'candidate_id','model_manifest_sha256'}
            and isinstance(base_ref['candidate_id'],str)
            and isinstance(base_ref['model_manifest_sha256'],str)
            and re.fullmatch(r'[a-f0-9]{64}',base_ref['model_manifest_sha256']) is not None))
        content={k:v for k,v in comparison.items() if k!='comparison_sha256'}
        target={'candidate_id':record['candidate_id'],'model_manifest_sha256':record['model_manifest_sha256']}
        valid=(base_ref_valid and isinstance(review.get('reviewed_at'),str)
               and comparison['profile']=='cospace.preview-candidate-comparison/0.1'
               and comparison['comparison_sha256']==checksum(content)
               and comparison['target_ref']==target
               and comparison['selection_revision']==record['selection_revision']-1
               and comparison['review_allowed'] is True
               and all(comparison.get(k)==record.get(k) for k in ('space_id','project_id'))
               and review['acknowledge_unverified'] is True and bool(review['note'].strip()))
        if valid and requested_base:
            matches=comparison['base_ref']=={'candidate_id':requested_base['candidate_id'],
                                            'model_manifest_sha256':requested_base['model_manifest_sha256']}
    except (KeyError,TypeError,ValueError,AttributeError):
        valid=False
    return {'status':'internally_consistent' if valid else 'binding_mismatch',
            'matches_requested_base_model':matches,'saved_review':review if isinstance(review,dict) else None,
            'trust':'saved_local_record_not_authenticated_approval'}


def compare_publications(publications,request):
    ownership=scope(publications.jobs.directory,request.space_id)
    base,old,base_ref=read_fixed(publications,request.base_publication_id,ownership)
    target,new,target_ref=read_fixed(publications,request.target_publication_id,ownership)
    changes=compare_models(old,new,0,ownership)
    report={'profile':'cospace.preview-publication-comparison/0.1',**ownership,
            'base_publication':base_ref,'target_publication':target_ref,
            'direction':'explicit_base_to_target_not_automatic_chronology',
            'geometry_comparable':changes['review_allowed'],
            'changes':{k:changes[k] for k in ('coordinate','geometry','ontology','objects','business','relations','dual_view_impact','comparison_scope')},
            'provenance':{'base':review_provenance(base,None),'target':review_provenance(target,base)},
            'quality':'unverified','robot_ready':False}
    # Recheck record bytes too: provenance is part of this comparison's fixed inputs.
    for record,model,ref in [(base,old,report['base_publication']),(target,new,report['target_publication'])]:
        if digest(model.root/'publication.json')!=ref['publication_record_sha256']:
            raise ValueError('publication_record_changed')
        if digest(model.root/'model.json')!=ref['model_manifest_sha256']:
            raise ValueError('publication_model_changed')
    return {**report,'comparison_sha256':checksum(report)}
