"""Fixed local candidate preview API. Deliberately separate from production releases."""
import argparse
import sqlite3
from typing import Literal
from pathlib import Path
from fastapi import FastAPI,HTTPException,Response,Request
from fastapi.responses import FileResponse,JSONResponse
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field,StrictFloat,StrictInt
import uvicorn
import numpy as np
from packages.construction.preview_model import PreviewModel,digest
from packages.construction.preview_jobs import PreviewJobs
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.preview_offline import export_bundle,sha,bundle_profile
from packages.views.agent.partitioned_preview import export_partitions
from packages.service.preview_checklist import checklist
from packages.service.preview_workflow import workflow
from packages.data.preview_inputs import PreviewInputs
from packages.data.preview_batches import PreviewBatches,BatchDraft,BatchChange,batch_results
from packages.data.preview_preflight import preflight
from packages.data.preview_artifacts import artifact_catalog
from packages.lifecycle.preview_impact import impact
from packages.lifecycle.preview_control import ControlChange
from packages.service.preview_lineage import lineage
from packages.data.preview_registration import PreviewRegistration
from packages.data.preview_source_config import load_sources
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.lifecycle.preview_scope import scope,owned
from packages.ontology.preview_versions import PreviewOntologies
from packages.spatial.preview_objects import SemanticRequest
from packages.construction.preview_semantics import annotate,ObjectRulesFailed
from packages.construction.preview_changes import CompareRequest,ReviewRequest,compare,confirm
from packages.service.preview_publication_changes import PublicationCompareRequest,compare_publications
from experiments.scripts.build_nyu_short_scene import png
from packages.spatial.preview_range import DEFAULT_RANGE_CELLS,MAX_RANGE_CELLS
from packages.data.preview_ledger import PreviewLedger
from packages.spatial.preview_business import LedgerDraft,BusinessRequest
from packages.construction.preview_business import associate
from packages.construction.preview_relations import relate
from packages.spatial.preview_relations import RelationRequest,RelationDraft
from packages.ontology.preview_relations import inspect_relations


class Query(BaseModel):
    point_m:list[float]


class RangeQuery(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    bounds_m:tuple[tuple[StrictFloat,StrictFloat,StrictFloat],tuple[StrictFloat,StrictFloat,StrictFloat]]
    frame_id:str=Field(strict=True,min_length=1,max_length=256)
    limit:StrictInt=Field(default=DEFAULT_RANGE_CELLS,ge=1,le=MAX_RANGE_CELLS)


class Selection(BaseModel):
    model_config=ConfigDict(extra="forbid")
    space_id:str|None=None
    candidate_id:str
    expected_revision:int


class BuildInfo(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(default='',max_length=100)
    purpose:str=Field(default='',max_length=500)
    changes:str=Field(default='',max_length=500)


class BuildRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    space_id:str|None=None
    input_id:str|None=None
    build_info:BuildInfo|None=None
    input_revision:StrictInt|None=Field(default=None,ge=0)
    batch_id:str|None=Field(default=None,pattern=r'^batch-[a-f0-9]{16}$')
    batch_revision:StrictInt|None=Field(default=None,ge=0)


class BuildInfoUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    space_id:str
    candidate_id:str
    expected_revision:StrictInt=Field(ge=0)
    build_info:BuildInfo


class BuildRetryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    space_id:str=Field(min_length=1,max_length=100)
    retry_of:str=Field(pattern=r'^build-[A-Za-z0-9-]+$')
    request_id:str=Field(pattern=r'^[a-f0-9]{32}$')


class ViewDerivationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    space_id:str=Field(min_length=1,max_length=100)
    candidate_id:str=Field(pattern=r'^build-[A-Za-z0-9-]+$')
    view_kind:Literal['human','agent']
    request_id:str=Field(pattern=r'^[a-f0-9]{32}$')


class RegistrationRequest(BaseModel):
    space_id:str|None=None
    model_config=ConfigDict(extra='forbid')
    source_id:str=Field(min_length=1,max_length=100)
    label:str=Field(min_length=1,max_length=100)


class ProjectRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=100)


class SpaceRequest(ProjectRequest):
    project_id:str=Field(min_length=1,max_length=100)
    description:str=Field(default='',max_length=500)


class OntologyValidationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    objects:list[dict]=Field(min_length=1,max_length=100)
    relations:list[RelationDraft]|None=Field(default=None,max_length=200)


def create_app(root,jobs=None,update_evidence=None,registration_sources=None,source_config_status=None,space_directory=None,ontologies=None,ledger=None,platform_origin=None):
    if jobs is not None:jobs.ontology_store=ontologies
    if root is None and (jobs is None or not platform_origin):
        raise ValueError('empty_runtime_requires_authorized_business_configuration')
    model=PreviewModel(root) if root is not None else None
    app=FastAPI(title='CoSpace local model flow preview')
    def initial_model():
        if model is None:raise HTTPException(404,'no_initial_model')
        return model
    from packages.service.platform_auth_http import disabled_auth_routes
    disabled_auth_routes(app)
    if jobs and space_directory:
        jobs.directory=space_directory
        if jobs.inputs: jobs.inputs.directory=space_directory
    if jobs and jobs.inputs and (jobs.batches is None or jobs.batches.inputs is not jobs.inputs):
        jobs.batches=PreviewBatches(jobs.inputs)
    publications=PreviewPublications(jobs) if jobs else None
    if root is not None and ((Path(root)/'publication.json').is_file() or publications and Path(root).resolve().is_relative_to(publications.root.resolve())):
        raise ValueError('publication_root_static_alias_not_supported')
    @app.middleware('http')
    async def distribution_gate(request,call_next):
        # Cover every method and suffix before routing, redirects, conditional/range and static fallback.
        parts=[part for part in request.scope['path'].replace('\\','/').split('/') if part]
        release_path=bool(parts and parts[0]=='publications')
        if release_path and len(parts)>1:
            try:
                if publications is None:raise ValueError('publication_not_found')
                await run_in_threadpool(publications.require_distributing,parts[1])
            except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:
                from packages.service.public_errors import public_error
                code=public_error(exc,('publication_retired','publication_distribution_paused','publication_not_found'),
                                  'publication_distribution_unavailable')
                if code=='publication_retired':
                    state=await run_in_threadpool(publications.distribution,parts[1])
                    return JSONResponse({'detail':'publication_retired','replacement_publication_id':state.get('replacement_publication_id'),
                        'reason':state.get('retirement_reason')},status_code=409,headers={'Cache-Control':'no-store'})
                return JSONResponse({'detail':code},status_code=404 if code=='publication_not_found' else 409,headers={'Cache-Control':'no-store'})
        response=await call_next(request)
        if release_path or request.url.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        return response
    registration=PreviewRegistration(jobs.inputs,registration_sources or {}) if jobs and jobs.inputs else None
    app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:8766','http://localhost:8766'],
                       allow_methods=['GET','POST'],allow_headers=['Content-Type'])
    def check_origin(request):
        if platform_origin is not None:
            if request.headers.get('origin') != platform_origin:raise HTTPException(403,'origin_not_allowed')
            return
        if request.headers.get('origin') not in (None,'http://127.0.0.1:8766','http://localhost:8766',
                                                'http://127.0.0.1:8767','http://localhost:8767'):
            raise HTTPException(403,'origin_not_allowed')
    def ontology_store(request=None):
        if request is not None and getattr(request.state,'ontology_store',None) is not None:return request.state.ontology_store
        if ontologies is None: raise HTTPException(503,'ontology_store_not_configured')
        return ontologies
    @app.get('/api/ledger')
    def ledger_list(space_id:str):
        validate_space(space_id)
        if ledger is None:raise HTTPException(503,'ledger_not_configured')
        try:return {'records':ledger.list(space_id),'space_id':space_id,'quality':'unverified'}
        except (OSError,ValueError,KeyError,TypeError) as exc:raise HTTPException(409,'ledger_unavailable') from exc
    @app.post('/api/ledger',status_code=201)
    def ledger_register(body:LedgerDraft,request:Request):
        check_origin(request)
        if ledger is None:raise HTTPException(503,'ledger_not_configured')
        try:return ledger.register(body)
        except (OSError,ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc
    @app.post('/api/business-candidates',status_code=201)
    def business_candidate(body:BusinessRequest,request:Request):
        check_origin(request)
        if ledger is None or jobs is None:raise HTTPException(503,'ledger_not_configured')
        try:return associate(jobs,ontology_store(request),ledger,body)
        except (OSError,ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc
    @app.post('/api/relation-candidates',status_code=201)
    def relation_candidate(body:RelationRequest,request:Request):
        check_origin(request)
        if jobs is None:raise HTTPException(503,'builds_not_configured')
        try:return relate(jobs,ontology_store(request),body)
        except ObjectRulesFailed as exc:raise HTTPException(422,exc.report) from exc
        except (OSError,ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc
    def ontology_error(exc):
        code=str(exc)
        if code not in ('ontology_not_found','ontology_reference_mismatch','ontology_integrity_changed',
                        'ontology_definition_invalid','ontology_relations_not_available'):
            code='ontology_integrity_changed'
        return HTTPException(404 if code=='ontology_not_found' else 409,code)
    @app.get('/api/ontologies')
    def list_ontologies(request:Request):
        try: return {'ontologies':ontology_store(request).list(),'scope':'shared_templates_and_current_workspace_rules'}
        except (ValueError,OSError,KeyError,TypeError) as exc: raise ontology_error(exc) from exc
    @app.get('/api/ontologies/{identity}/{version}')
    def read_ontology(identity:str,version:str,sha256:str,request:Request):
        try:
            record,value=ontology_store(request).read(identity,version,sha256)
            return {'record':record,'definition':value,'integrity':'verified',
                    'scope':'workspace_rules' if record.get('authoring') else 'shared_template'}
        except (ValueError,OSError,KeyError,TypeError) as exc: raise ontology_error(exc) from exc
    @app.post('/api/ontologies/{identity}/{version}/validate')
    def validate_ontology(identity:str,version:str,body:OntologyValidationRequest,request:Request):
        check_origin(request)
        try:
            report=ontology_store(request).inspect(identity,version,body.sha256,body.objects)
            if body.relations is not None:
                if report['status']=='passed':
                    _,definition=ontology_store(request).read(identity,version,body.sha256)
                    if not definition.get('relations'):raise ValueError('ontology_relations_not_available')
                    checked=inspect_relations(definition,body.objects,[r.model_dump() for r in body.relations])
                    report.update(status=checked['status'],issues=checked['issues'])
                report['relation_count']=len(body.relations)
            return report
        except (ValueError,OSError,KeyError,TypeError) as exc: raise ontology_error(exc) from exc
    @app.post('/api/semantic-candidates',status_code=201)
    def semantic_candidate(body:SemanticRequest,request:Request):
        check_origin(request)
        if jobs is None:raise HTTPException(503,'builds_not_configured')
        try:return annotate(jobs,ontology_store(request),body)
        except ObjectRulesFailed as exc:raise HTTPException(409,{'code':'object_rules_failed','issues':exc.report['issues']}) from exc
        except (ValueError,OSError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc
    def object_query(current,identity=None):
        try:return current.objects(identity)
        except ValueError as exc:raise HTTPException(404 if str(exc) in ('object_not_found','semantic_objects_not_available') else 409,str(exc)) from exc
    def validate_space(space_id):
        try: return scope(space_directory,space_id)
        except (ValueError,OSError) as exc: raise HTTPException(404,'space_not_found') from exc
    def filtered(records,space_id):
        validate_space(space_id)
        return [r for r in records if r.get('space_id')==space_id]
    def directory():
        if space_directory is None: raise HTTPException(503,'space_directory_not_configured')
        return space_directory
    @app.get('/api/projects')
    def projects(): return {'projects':directory().list('project')}
    @app.get('/api/spaces')
    def spaces():
        records=distribution_entries()
        # Latest fixed preview is an explicit directory entry, never a candidate pointer.
        result=[]
        for s in directory().list('space'):
            related=[p for p in records if p.get('space_id')==s['id']]
            result.append({**s,'publications':related,**space_entry(related)})
        return {'spaces':result,
                'legacy_records':'unassigned'}
    @app.get('/api/projects/{identity}')
    def project(identity:str):
        try: return directory().read('project',identity)
        except (ValueError,OSError) as exc: raise HTTPException(404,'project_not_found') from exc
    @app.get('/api/spaces/{identity}')
    def space(identity:str):
        try:
            record=directory().read('space',identity)
            related=[p for p in distribution_entries() if p.get('space_id')==identity]
            return {**record,**space_entry(related)}
        except (ValueError,OSError) as exc: raise HTTPException(404,'space_not_found') from exc
    @app.post('/api/projects',status_code=201)
    def create_project(body:ProjectRequest,request:Request):
        check_origin(request)
        try: return directory().create('project',body.name)
        except (ValueError,OSError) as exc: raise HTTPException(409,'project_creation_failed') from exc
    @app.post('/api/spaces',status_code=201)
    def create_space(body:SpaceRequest,request:Request):
        check_origin(request)
        try: return directory().create('space',body.name,body.project_id,body.description)
        except (ValueError,OSError) as exc: raise HTTPException(409,'space_creation_failed_check_project_and_name') from exc
    @app.get('/api/publications')
    def list_publications(space_id:str|None=None):
        return {'publications':filtered(distribution_entries(),space_id)}
    def distribution_entries():
        try:return publications.directory_entries() if publications else []
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise HTTPException(409,'publication_distribution_unavailable') from exc
    def space_entry(related):
        if not related:return {'publication_id':None,'state':'no_publication'}
        latest=related[0]
        return {'publication_id':latest['id'] if latest['lifecycle_state']=='active' else None,
                'state':'preview_published' if latest['lifecycle_state']=='active' else 'distribution_paused'}
    @app.post('/api/publications',status_code=201)
    def publish(body:Selection,request:Request):
        check_origin(request)
        if publications is None: raise HTTPException(503,'builds_not_configured')
        try: return publications.publish(body.candidate_id,body.expected_revision,body.space_id)
        except (ValueError,OSError) as exc: raise HTTPException(409,str(exc)) from exc
    @app.post('/api/publication-comparisons')
    def publication_comparison(body:PublicationCompareRequest,request:Request):
        check_origin(request)
        if publications is None: raise HTTPException(503,'builds_not_configured')
        try:
            publications.require_distributing(body.base_publication_id);publications.require_distributing(body.target_publication_id)
            return compare_publications(publications,body)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc: raise HTTPException(409,'publication_distribution_unavailable' if isinstance(exc,sqlite3.Error) else str(exc)) from exc
    def publication(identity):
        try:
            if publications is None: raise ValueError('publication_not_found')
            return publications.read(identity)
        except (ValueError,OSError) as exc: raise HTTPException(409,str(exc)) from exc
    @app.get('/publications/{identity}/api/preview')
    def publication_model(identity:str):
        record,current=publication(identity)
        return {**current.manifest,'publication':record,'service_state':'preview_published'}
    @app.get('/publications/{identity}/api/objects')
    @app.get('/publications/{identity}/api/objects/{object_id}')
    def publication_objects(identity:str,object_id:str|None=None):
        record,current=publication(identity)
        return {**object_query(current,object_id),'publication_id':identity,
                'publication_model_manifest_sha256':record['model_manifest_sha256']}
    @app.get('/publications/{identity}/api/checklist')
    def publication_checklist(identity:str):
        if publications is None: raise HTTPException(404,'publication_not_found')
        try: return checklist(publications,identity,update_evidence)
        except (ValueError,OSError,KeyError) as exc: raise HTTPException(409,str(exc)) from exc
    @app.get('/publications/{identity}/api/provenance')
    def publication_provenance(identity:str):
        if publications is None: raise HTTPException(404,'publication_not_found')
        try:
            return JSONResponse(lineage(publications,identity,provenance=True),headers={'Cache-Control':'no-store'})
        except (ValueError,OSError,KeyError,TypeError) as exc:
            raise HTTPException(409,'publication_provenance_unavailable') from exc
    @app.get('/publications/{identity}/api/lineage')
    def publication_lineage(identity:str):
        if publications is None: raise HTTPException(404,'publication_not_found')
        try: return lineage(publications,identity)
        except (ValueError,OSError,KeyError) as exc: raise HTTPException(409,str(exc)) from exc
    @app.post('/publications/{identity}/api/query')
    def publication_query(identity:str,body:Query):
        record,current=publication(identity)
        try: result=current.query(body.point_m)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        return {**result,'publication_id':identity,'publication_model_manifest_sha256':record['model_manifest_sha256'],**owned(record)}
    @app.post('/publications/{identity}/api/query-range')
    def publication_range(identity:str,body:RangeQuery):
        record,current=publication(identity)
        try:result=current.query_range(body.bounds_m,body.frame_id,body.limit)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        return {**result,'publication_id':identity,'publication_model_manifest_sha256':record['model_manifest_sha256'],**owned(record)}
    @app.get('/publications/{identity}/')
    def publication_index(identity:str): return FileResponse(publication(identity)[1].root/'index.html')
    @app.get('/publications/{identity}/offline.zip')
    def publication_bundle(identity:str):
        record,current=publication(identity)
        data=export_bundle(record,current)
        return Response(data,media_type='application/zip',headers={
            'Content-Disposition':f'attachment; filename="{identity}-offline.zip"',
            'X-CoSpace-Package-SHA256':sha(data)})
    @app.get('/publications/{identity}/offline.json')
    def publication_bundle_info(identity:str):
        record,current=publication(identity)
        data=export_bundle(record,current)
        semantic=bool(current.manifest.get('semantic_annotation'))
        return {'profile':bundle_profile(current),'publication_id':identity,
                **owned(record),
                'download_url':record['preview_url']+'offline.zip',
                'sha256':sha(data),'bytes':len(data),'quality':'unverified','robot_ready':False,
                'contents':['package.json','publication.json','model.json','agent.npz']+(['objects.json','ontology.json'] if semantic else [])+(['business.json'] if current.manifest.get('business_association') else [])+(['relations.json'] if current.manifest.get('object_relations') else [])}
    def partition_delivery(identity):
        record,current=publication(identity)
        try:return export_partitions(record,current)
        except (ValueError,OSError,KeyError,TypeError,OverflowError) as exc:
            raise HTTPException(409,'partition_delivery_unavailable') from exc
    @app.get('/publications/{identity}/partitions.json')
    def publication_partitions_info(identity:str):
        _,info=partition_delivery(identity)
        return {**info,'download_url':f'/publications/{identity}/partitions.zip'}
    @app.get('/publications/{identity}/partitions.zip')
    def publication_partitions(identity:str):
        data,info=partition_delivery(identity)
        return Response(data,media_type='application/zip',headers={
            'Content-Disposition':f'attachment; filename="{identity}-partitions.zip"',
            'X-CoSpace-Package-SHA256':info['sha256'],'X-CoSpace-Index-SHA256':info['index_sha256']})
    @app.get('/publications/{identity}/{name}')
    def publication_file(identity:str,name:str):
        record,current=publication(identity)
        if name not in {*record['files'],'publication.json'}: raise HTTPException(404)
        return FileResponse(current.root/name)
    @app.get('/api/selection')
    def selection(space_id:str|None=None):
        validate_space(space_id)
        return jobs.selection(space_id) if jobs else {'revision':0,'candidate_id':None}
    @app.post('/api/selection')
    def select(body:Selection,request:Request):
        check_origin(request)
        if jobs is None: raise HTTPException(503,'builds_not_configured')
        try: return jobs.select(body.candidate_id,body.expected_revision,body.space_id)
        except (ValueError,OSError) as exc: raise HTTPException(409,str(exc)) from exc
    @app.post('/api/candidate-comparisons')
    def candidate_comparison(body:CompareRequest,request:Request):
        check_origin(request)
        if jobs is None: raise HTTPException(503,'builds_not_configured')
        try: return compare(jobs,body)
        except (ValueError,OSError,KeyError) as exc: raise HTTPException(409,str(exc)) from exc
    @app.post('/api/candidate-reviews')
    def candidate_review(body:ReviewRequest,request:Request):
        check_origin(request)
        if jobs is None: raise HTTPException(503,'builds_not_configured')
        try: return confirm(jobs,body)
        except (ValueError,OSError,KeyError) as exc: raise HTTPException(409,str(exc)) from exc
    @app.get('/api/workspace-model')
    def workspace_model(space_id:str|None=None):
        selected=selection(space_id)
        if not selected['candidate_id']:
            if space_id is not None: raise HTTPException(404,'space_has_no_selected_candidate')
            return {**initial_model().manifest,'selection':selected,'preview_url':'/','thumbnail_url':'/api/thumbnail'}
        current=candidate(selected['candidate_id'])
        if digest(current.root/'model.json')!=selected['model_manifest_sha256']:
            raise HTTPException(409,'selected_model_integrity_changed')
        return {**current.manifest,'selection':selected,'preview_url':selected['candidate_url'],
                'thumbnail_url':selected['candidate_url']+'api/thumbnail'}
    @app.get('/api/builds')
    def builds(space_id:str|None=None):
        entries=controlled_entries(filtered(jobs.list() if jobs else [],space_id),space_id,'candidate')
        if jobs and jobs.inputs:
            for entry in entries:
                if not entry.get('input_binding'):continue
                try:
                    current=jobs.inputs.read(entry['input_id']).get('coordinate_revision',{}).get('revision',0)
                    fixed=entry['input_binding'].get('coordinate_revision',{}).get('revision',0)
                    if current!=fixed:entry['input_revision_status']='historical_requires_rebuild_for_current'
                except (ValueError,RuntimeError,OSError,KeyError):entry['input_revision_status']='unavailable'
        return {'jobs':entries,'enabled':jobs is not None}
    @app.get('/api/artifacts')
    def artifacts(space_id:str|None=None):
        validate_space(space_id)
        if publications is None:raise HTTPException(503,'builds_not_configured')
        try:return artifact_catalog(publications,space_id)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise HTTPException(409,'artifact_catalog_unavailable') from exc
    @app.get('/api/workflow')
    def current_workflow(space_id:str,job_id:str|None=None,publication_id:str|None=None):
        validate_space(space_id)
        if publications is None:raise HTTPException(503,'builds_not_configured')
        try:return workflow(publications,space_id,job_id,publication_id)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise HTTPException(409,'workflow_unavailable_refresh_required') from exc
    @app.get('/api/artifact-impact')
    def artifact_impact(space_id:str,artifact:str):
        validate_space(space_id)
        if publications is None:raise HTTPException(503,'builds_not_configured')
        try:return impact(publications,space_id,artifact)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:
            code=str(exc)
            status=404 if code=='impact_artifact_not_found' else 422 if code in ('impact_artifact_invalid','impact_kind_not_supported') else 409
            raise HTTPException(status,code if code.startswith('impact_') else 'impact_records_unavailable') from exc
    @app.get('/api/artifact-control')
    def artifact_control(space_id:str,artifact:str):
        validate_space(space_id)
        if publications is None:raise HTTPException(503,'builds_not_configured')
        try:return jobs.controls.report(publications,space_id,artifact)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise control_error(exc) from exc
    def control_error(exc):
        code=str(exc)
        status=404 if code=='impact_artifact_not_found' else 422 if code=='lifecycle_artifact_invalid' else 409
        return HTTPException(status,code if code.startswith(('lifecycle_','impact_')) else 'lifecycle_records_unavailable')
    @app.post('/api/artifact-control/transitions')
    def artifact_control_change(body:ControlChange,request:Request):
        check_origin(request);validate_space(body.space_id)
        if publications is None:raise HTTPException(503,'builds_not_configured')
        try:return jobs.controls.change(publications,body)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise control_error(exc) from exc
    @app.get('/api/inputs')
    def inputs(space_id:str|None=None):
        return {'inputs':controlled_entries(filtered(jobs.inputs.list() if jobs and jobs.inputs else [],space_id),space_id,'input'),
                'selection_required':bool(jobs and jobs.inputs is not None)}
    def controlled_entries(entries,space_id,kind):
        if not space_id or jobs is None:return entries
        try:
            saved={r['artifact']:r for r in jobs.controls.saved(space_id)}
            return [{**entry,'lifecycle_state':saved.get(kind+':'+entry['id'],{}).get('lifecycle_state','active')} for entry in entries]
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise HTTPException(409,'lifecycle_records_unavailable') from exc
    def batch_store():
        if jobs is None or jobs.batches is None:raise HTTPException(503,'batches_not_configured')
        return jobs.batches
    @app.get('/api/batches')
    def list_batches(space_id:str):
        validate_space(space_id)
        try:return {'batches':batch_store().list(space_id),'space_id':space_id}
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise HTTPException(409,'batch_store_unavailable' if isinstance(exc,sqlite3.Error) else str(exc)) from exc
    @app.get('/api/batches/{identity}')
    def read_batch(identity:str,space_id:str):
        validate_space(space_id)
        try:return batch_results(batch_store(),jobs,publications,identity,space_id)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise HTTPException(409,'batch_store_unavailable' if isinstance(exc,sqlite3.Error) else str(exc)) from exc
    @app.post('/api/batches',status_code=201)
    def create_batch(body:BatchDraft,request:Request):
        check_origin(request);validate_space(body.space_id)
        try:return batch_store().create(body)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise HTTPException(409,'batch_store_unavailable' if isinstance(exc,sqlite3.Error) else str(exc)) from exc
    @app.post('/api/batches/{identity}/transitions')
    def change_batch(identity:str,body:BatchChange,request:Request):
        check_origin(request);validate_space(body.space_id)
        try:return batch_store().change(identity,body)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:raise HTTPException(409,'batch_store_unavailable' if isinstance(exc,sqlite3.Error) else str(exc)) from exc
    @app.get('/api/registration-sources')
    def registration_options():
        result={'sources':registration.list() if registration else []}
        if source_config_status is not None: result['configuration']=source_config_status
        return result
    @app.post('/api/inputs')
    def register_input(body:RegistrationRequest,request:Request,response:Response):
        check_origin(request)
        if registration is None: raise HTTPException(503,'input_catalog_not_configured')
        try:
            result=registration.register(body.source_id,body.label,body.space_id)
            response.status_code=201 if result['created'] else 200
            return result
        except (ValueError,OSError,KeyError,TypeError,IndexError) as exc:
            code=str(exc) if str(exc) in ('registration_source_not_allowed','invalid_input_label','space_not_found','invalid_space_record') else 'registration_validation_failed'
            raise HTTPException(409,code) from exc
    def registered_input(identity):
        if not jobs or jobs.inputs is None: raise HTTPException(503,'input_catalog_not_configured')
        try: return jobs.inputs.read(identity)
        except (ValueError,OSError,KeyError) as exc: raise HTTPException(404,'input_not_found') from exc
    @app.get('/api/inputs/{identity}')
    def input_detail(identity:str):
        record=registered_input(identity)
        from packages.data.input_routes import route
        record=record|{'route':route(record['format'])}
        if record['format']=='ply_pointcloud':
            return {**record,'supported_format':'PLY已有点云 · 显式坐标声明',
                    'limitations':['保留输入坐标，不执行配准或SLAM','坐标声明与来源由资料提供者给出，未独立复核','无彩色属性时采用中性显示','不推断空闲或可通行区域，不执行精度验收']}
        if record['format']=='ros1_lidar_multiframe_icp':
            return {**record,'supported_format':'ROS1激光样本 · 多帧局部建图',
                    'limitations':['纯激光ICP估计逐帧位姿；IMU和参考位姿不参与融合','首帧局部基准；未对齐现场坐标、未做回环或运动畸变补偿','灰度来自强度，不是相机彩色','精度、时钟同步与可通行性未验收']}
        if record['format']=='ros1_lidar_single_frame':
            return {**record,'supported_format':'ROS1激光样本 · 单帧局部候选',
                    'limitations':['仅首帧点云用于候选，其余帧和IMU仅作输入核对','传感器局部坐标，未配准、未执行SLAM','灰度来自强度，不是相机彩色','不执行精度与完整度验收']}
        return {**record,'supported_format':'NYU封存RGB-D + 已有轨迹',
                'limitations':['仅支持640×480 PGM深度与PPM彩色图像','不生成新轨迹','不执行精度与完整度验收']}
    @app.post('/api/inputs/{identity}/preflight')
    def input_preflight(identity:str,request:Request):
        check_origin(request)
        registered_input(identity)
        return preflight(jobs.inputs,identity)
    @app.post('/api/builds',status_code=202)
    def start_build(request:Request,body:BuildRequest|None=None):
        check_origin(request)
        if jobs is None: raise HTTPException(503,'builds_not_configured')
        try: return jobs.start(body.input_id if body else None,body.space_id if body else None,
                               body.batch_id if body else None,body.batch_revision if body else None,
                               **({'build_info':body.build_info.model_dump()} if body and body.build_info is not None else {}),
                               **({'input_revision':body.input_revision} if body and body.input_revision is not None else {}))
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc: raise HTTPException(409,'batch_store_unavailable' if isinstance(exc,sqlite3.Error) else str(exc)) from exc
    @app.post('/api/build-info')
    def update_build_info(request:Request,body:BuildInfoUpdate):
        check_origin(request)
        if jobs is None:raise HTTPException(503,'builds_not_configured')
        try:return jobs.update_info(body.space_id,body.candidate_id,body.build_info.model_dump(),body.expected_revision)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc
    @app.post('/api/build-retries')
    def retry_build(request:Request,body:BuildRetryRequest):
        check_origin(request)
        if jobs is None:raise HTTPException(503,'builds_not_configured')
        try:
            result=jobs.retry(body.space_id,body.retry_of,body.request_id)
            return JSONResponse(result,status_code=202 if result['created'] else 200)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:
            # Do not expose local source paths in missing/unreadable-file errors.
            code='retry_input_file_unavailable' if isinstance(exc,OSError) else 'batch_store_unavailable' if isinstance(exc,sqlite3.Error) else str(exc)
            raise HTTPException(409,code) from exc
    @app.get('/api/build-stages')
    def build_stages(space_id:str,candidate_id:str):
        if jobs is None:raise HTTPException(503,'builds_not_configured')
        try:return jobs.stages(space_id,candidate_id)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise HTTPException(409,'build_stages_unavailable') from exc
    @app.post('/api/view-derivations')
    def derive_view(request:Request,body:ViewDerivationRequest):
        check_origin(request)
        if jobs is None:raise HTTPException(503,'builds_not_configured')
        try:
            result=jobs.derive_view(body.space_id,body.candidate_id,body.view_kind,body.request_id)
            return JSONResponse(result,status_code=202 if result['created'] else 200)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:
            raise HTTPException(409,'view_files_unavailable' if isinstance(exc,OSError) else 'view_store_unavailable' if isinstance(exc,sqlite3.Error) else str(exc)) from exc
    def candidate(identity):
        try:
            if jobs is None: raise ValueError('builds_not_configured')
            return jobs.model(identity)
        except ValueError as exc: raise HTTPException(404,str(exc)) from exc
    @app.get('/candidates/{identity}/api/preview')
    def candidate_manifest(identity:str): return {**candidate(identity).manifest,'service_state':'preview_served'}
    @app.get('/candidates/{identity}/api/anchor-preview')
    def candidate_anchor_preview(identity:str):
        from packages.data.input_preview import sample,bounded
        from packages.construction.preview_model import digest
        current=candidate(identity)
        if not isinstance(current.manifest.get('axes'),list) or len(current.manifest['axes'])!=3:
            raise HTTPException(409,'anchor_coordinate_axes_unavailable')
        with np.load(current.root/'spatial.npz',allow_pickle=False) as arrays:
            points=arrays['points'];colors=arrays['colors']
        return bounded({'profile':'cospace.anchor-preview/0.1','candidate_id':identity,
            'space_id':current.manifest['space_id'],'source_sha256':current.manifest['members']['spatial.npz']['sha256'],
            'manifest_sha256':digest(current.root/'model.json'),'frame_id':current.manifest['frame_id'],
            'axes':current.manifest['axes'],'unit':'m','appearance':current.manifest.get('appearance','source_rgb'),
            'quality':'unverified','robot_ready':False,**sample(points,colors)})

    @app.get('/candidates/{identity}/api/anchor')
    def candidate_anchor(identity:str,point_index:int=0):
        current=candidate(identity)
        with np.load(current.root/'spatial.npz',allow_pickle=False) as arrays:points=arrays['points']
        if not 0<=point_index<len(points):raise HTTPException(422,'object_point_index_out_of_range')
        return {'candidate_id':identity,'model_manifest_sha256':digest(current.root/'model.json'),
                'has_semantic_objects':bool(current.manifest.get('semantic_annotation')),
                'point_index':point_index,'point_count':len(points),'anchor_m':points[point_index].astype(float).tolist(),
                'frame_id':current.manifest['frame_id'],'source_model_sha256':current.manifest['members']['spatial.npz']['sha256'],
                **owned(current.manifest)}
    @app.get('/candidates/{identity}/api/objects')
    @app.get('/candidates/{identity}/api/objects/{object_id}')
    def candidate_objects(identity:str,object_id:str|None=None):return object_query(candidate(identity),object_id)
    @app.post('/candidates/{identity}/api/query')
    def candidate_query(identity:str,body:Query):
        try: return candidate(identity).query(body.point_m)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    @app.get('/candidates/{identity}/')
    def candidate_index(identity:str): return FileResponse(candidate(identity).root/'index.html')
    @app.get('/candidates/{identity}/{name}')
    def candidate_file(identity:str,name:str):
        m=candidate(identity)
        if name not in {*m.manifest['members'],'model.json','offline-checks.json'}: raise HTTPException(404)
        return FileResponse(m.root/name)
    @app.get('/api/thumbnail')
    def thumbnail():
        return model_thumbnail(initial_model())
    @app.get('/candidates/{identity}/api/thumbnail')
    def candidate_thumbnail(identity:str): return model_thumbnail(candidate(identity))
    def model_thumbnail(current):
        with np.load(current.root/'spatial.npz',allow_pickle=False) as arrays:
            points=arrays['points']; colors=arrays['colors']
        image=np.full((360,640,3),[11,16,25],dtype=np.uint8)
        # Existing scene coordinates have no RGB-D camera origin or forward axis.
        # Fit their whole extent for display without changing the model geometry.
        if current.manifest.get('data_kind') in ('real_lidar_sensor_local_candidate','existing_pointcloud_candidate'):
            projected=np.column_stack((.7*points[:,0]-.7*points[:,1],.35*points[:,0]+.35*points[:,1]-.9*points[:,2]))
            lo=projected.min(axis=0);hi=projected.max(axis=0);scale=min(600/max(hi[0]-lo[0],.001),320/max(hi[1]-lo[1],.001))
            pixels=np.rint((projected-(lo+hi)/2)*scale+[320,180]).astype(int)
            for (x,y),color in zip(pixels,colors):
                if 0<=x<640 and 0<=y<360:image[y,x]=color
            return Response(png(image),media_type='image/png')
        visible=points[:,2]>.1; points=points[visible]; colors=colors[visible]
        x=np.rint(points[:,0]/points[:,2]*430+320).astype(int)
        y=np.rint(points[:,1]/points[:,2]*430+180).astype(int)
        for i in np.argsort(-points[:,2]):
            if 0<=x[i]<640 and 0<=y[i]<360: image[y[i],x[i]]=colors[i]
        return Response(png(image),media_type='image/png')
    @app.get('/api/preview')
    def manifest(): return {**initial_model().manifest,'service_state':'preview_served'}
    @app.post('/api/query')
    def query(body:Query):
        try: return initial_model().query(body.point_m)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    workbench=Path('apps/workbench/dist')
    if workbench.is_dir(): app.mount('/workbench',StaticFiles(directory=workbench,html=True),name='workbench')
    if root is not None:app.mount('/',StaticFiles(directory=Path(root),html=True),name='preview')
    return app


def main():
    p=argparse.ArgumentParser(); p.add_argument('root',type=Path); p.add_argument('--port',type=int,default=8767)
    p.add_argument('--sources-config',type=Path,default=Path('deploy/config/preview-sources.json'))
    p.add_argument('--ontology-seed',type=Path,action='append',help='Repeat for multiple fixed rule versions; defaults to the two bundled versions')
    a=p.parse_args()
    try: allowed,config_status=load_sources(a.sources_config,Path.cwd())
    except (ValueError,OSError) as exc: p.exit(2,f'source_config_refused: {exc}\n')
    catalog=PreviewInputs(a.root.parent/'preview-inputs')
    jobs=PreviewJobs(a.root.parent/'preview-builds',Path('.'),Path('.'),catalog)
    spaces=PreviewSpaces(a.root.parent/'preview-directory')
    ontologies=PreviewOntologies(a.root.parent/'preview-ontologies')
    ledger=PreviewLedger(a.root.parent/'preview-ledger',spaces)
    try:
        for seed in a.ontology_seed or [Path('configs/ontology/indoor-equipment-v0.1.json'),Path('configs/ontology/indoor-equipment-v0.2.json')]:ontologies.register(seed)
    except (ValueError,OSError) as exc: p.exit(2,f'ontology_seed_refused: {exc}\n')
    uvicorn.run(create_app(a.root,jobs,Path('experiments/evidence/2026-10-29/nyu-update-001/checks.json'),allowed,config_status,spaces,ontologies,ledger),
                host='127.0.0.1',port=a.port)


if __name__=='__main__': main()
