"""Explicit deny-by-default authorization before the engineering business ASGI app."""
import json
import re
import sqlite3
from pydantic import ValidationError
from packages.lifecycle.workspace_scenes import WorkspaceScenes,CreateScene,WorkspaceScenesConflict,WorkspaceScenesUnavailable
from urllib.parse import unquote
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from packages.infrastructure.platform_identity import PlatformPrincipal, IdentityRejected, IdentityUnavailable
from packages.infrastructure.platform_subscription import SubscriptionDenied, SubscriptionUnavailable
from packages.service.platform_resource_access import PlatformResourceAccess
from packages.lifecycle.space_settings import SpaceSettingsChange, SettingsConflict, SettingsUnavailable
from packages.data.space_sources import SpaceSources, SourceChange, SourcesConflict, SourcesUnavailable
from packages.data.preview_registration import PreviewRegistration
from packages.data.preflight_records import PreflightRecords, PreflightUnavailable
from packages.data.input_descriptions import InputDescriptions, DescriptionChange, DescriptionConflict, DescriptionUnavailable
from packages.data.input_coordinates import InputCoordinates, CoordinateChange, CoordinatesConflict, CoordinatesUnavailable
from packages.data.input_routes import route
from packages.data.input_facts import facts, FactsUnavailable
from packages.data.input_preview import preview as input_preview,PreviewUnavailable
from packages.data.rgbd_input_preview import directory as rgbd_directory, frame as rgbd_frame
from packages.construction.build_preview import preview as build_preview
from packages.construction.build_process import read_process
from packages.service.space_preparation import preparation
from packages.data.input_uploads import InputUploads,UploadRejected,MAX_UPLOAD,capabilities as upload_capabilities,metadata as upload_metadata
from packages.ontology.workspace_authoring import WorkspaceOntologies,DraftChange,SealDraft


class BusinessAccess:
    def __init__(self, rp, policies, directory, jobs, registration_sources=None,workspace_config=None,consumer_config=None,subscriptions=None):
        self.rp,self.policies,self.directory,self.jobs=rp,policies,directory,jobs
        self.subscriptions=subscriptions
        self.sources=SpaceSources(directory.root,registration_sources or {})
        self.workspace_scenes=WorkspaceScenes(directory,policies,self.sources,workspace_config)
        self.registration=PreviewRegistration(jobs.inputs,{}) if jobs.inputs else None
        self.consumer=None
        if consumer_config is not None:
            from packages.service.online_consumer import OnlineConsumer
            self.consumer=OnlineConsumer(rp,policies,jobs,consumer_config,subscriptions=subscriptions)

    def require_subscription(self,session):
        if self.subscriptions is not None:
            principal=self.rp.verifier.verify(session['access_token'])
            return self.subscriptions.require(principal,session['access_token'],ui=True)

    def authorize(self, request, session, policy, body):
        principal=self.rp.verifier.verify(session['access_token'])
        access=PlatformResourceAccess(self.directory,self.jobs,policy)
        path=request.url.path; method=request.method; q=request.query_params
        if path=='/api/workspace-scenes' and method in ('GET','HEAD','POST'):
            context=self.workspace_scenes.context(principal)
            if method=='POST' and not context['can_create']:raise PermissionError()
            return {'principal':principal,'workspace_context':context}
        def space(identity,cap='space.preview'):
            return access.space(principal,identity,cap)
        def artifact(value,cap='space.preview',wanted=None):
            return access.artifact(principal,value,cap,requested_space=wanted)
        def references(cap):
            wanted=body.get('space_id');space(wanted,cap)
            for field in ('candidate_id','base_candidate_id'):
                if body.get(field):artifact('candidate:'+body[field],cap,wanted)
            for field in ('base_publication_id','target_publication_id'):
                if body.get(field):artifact('publication:'+body[field],cap,wanted)
            for value in body.get('input_ids') or []:artifact('input:'+value,cap,wanted)
            if body.get('input_id'):artifact('input:'+body['input_id'],'data.manage',wanted)
            return wanted
        def selected(wanted,cap):
            # Read saved selection; never poll or open geometry during authorization.
            selection=self.jobs.root/'space-selections'/(wanted+'.json')
            if selection.is_file():
                saved=json.loads(selection.read_bytes())
                if saved.get('space_id')!=wanted:raise PermissionError()
                if saved.get('candidate_id'):artifact('candidate:'+saved['candidate_id'],cap,wanted)
        def batch(identity,wanted,cap):
            space(wanted,cap)
            if self.jobs.batches is None:raise PermissionError()
            record=self.jobs.batches.read(identity,wanted)
            if record.get('space_id')!=wanted:raise PermissionError()

        visible=policy.visible(principal,self.directory.list('space')) if path in ('/api/projects','/api/spaces') or path.startswith('/api/projects/') else None
        if path in ('/api/ontology-authoring','/api/ontology-authoring/drafts','/api/ontology-authoring/validate','/api/ontology-authoring/seal'):
            if method not in ('GET','HEAD','POST'):raise PermissionError()
            if method=='POST' and not principal.workspace_owner:raise PermissionError()
            return {'principal':principal}
        if path=='/api/input-uploads' and method in ('GET','POST'):
            space(q.get('space_id'),'data.manage');return {'principal':principal}
        if path=='/api/build-preview' and method in ('GET','HEAD'):
            wanted=q.get('space_id');space(wanted,'build.run')
            artifact('candidate:'+str(q.get('candidate_id','')),'build.run',wanted)
            job=json.loads((self.jobs.root/q['candidate_id']/'job.json').read_bytes())
            if job.get('frozen_model'):artifact('candidate:'+job['frozen_model']['job_id'],'build.run',wanted)
            return {'principal':principal}
        if path=='/api/build-process' and method in ('GET','HEAD'):
            wanted=q.get('space_id');space(wanted,'build.run')
            artifact('candidate:'+str(q.get('candidate_id','')),'build.run',wanted)
            job=json.loads((self.jobs.root/q['candidate_id']/'job.json').read_bytes())
            artifact('input:'+str(job.get('input_id','')),'build.run',wanted)
            return {'principal':principal}
        rgbd_path=re.fullmatch(r'/api/inputs/([^/]+)/rgbd-preview(?:/frame)?',path)
        if rgbd_path and method in ('GET','HEAD'):
            wanted=q.get('space_id');space(wanted,'data.manage');artifact('input:'+rgbd_path[1],'data.manage',wanted)
            return {'principal':principal}
        metadata_path=re.fullmatch(r'/api/inputs/([^/]+)/(description|facts|preview|coordinates)',path)
        if metadata_path and (method in ('GET','HEAD') or method=='POST' and metadata_path[2] in ('description','coordinates')):
            wanted=body.get('space_id') if method=='POST' else q.get('space_id')
            space(wanted,'data.manage');artifact('input:'+metadata_path[1],'data.manage',wanted)
            return {'principal':principal}
        if path in ('/api/source-settings','/api/registration-sources') and method in ('GET','HEAD'):
            space(q.get('space_id'),'data.manage');return {'principal':principal}
        if path=='/api/source-settings' and method=='POST':
            space(body.get('space_id'),'space.manage');return {'principal':principal}
        if path=='/api/workflow' and method in ('GET','HEAD'):
            space(q.get('space_id'))
            if q.get('input_id'):artifact('input:'+q['input_id'],'data.manage',q.get('space_id'))
            if q.get('job_id'):artifact('candidate:'+q['job_id'],'build.run',q.get('space_id'))
            if q.get('publication_id'):artifact('publication:'+q['publication_id'],'space.preview',q.get('space_id'))
            return {'principal':principal}
        if path=='/api/space-settings':
            if method in ('GET','HEAD'):
                space(q.get('space_id'));return {'principal':principal}
            if method=='POST':
                space(body.get('space_id'),'space.manage');return {'principal':principal}
        if method in ('GET','HEAD') and path in ('/api/projects','/api/spaces'):
            return {'principal':principal,'visible':visible}
        if method in ('GET','HEAD') and path.startswith('/api/projects/'):
            identity=path.rsplit('/',1)[-1]
            if identity not in {s['project_id'] for s in visible}:raise PermissionError()
            return {'principal':principal}
        if method in ('GET','HEAD') and re.fullmatch(r'/api/spaces/[^/]+',path):
            space(path.rsplit('/',1)[-1]);return {'principal':principal}
        m=re.fullmatch(r'/(publications|candidates)/([^/]+)(/.*)?',path)
        if m:
            kind='publication' if m[1]=='publications' else 'candidate'; suffix=m[3] or '/'
            cap=None
            if method in ('GET','HEAD'):
                if suffix in ('/','/index.html','/human.ply','/views.js','/model.json','/objects.json','/ontology.json','/business.json','/relations.json',
                              '/api/preview','/api/thumbnail','/api/objects','/api/checklist','/api/lineage') or re.fullmatch(r'/api/objects/[^/]+',suffix):cap='space.preview'
                elif suffix in ('/api/anchor','/api/anchor-preview') and kind=='candidate':cap='association.edit'
                elif re.fullmatch(r'/[^/]+',suffix):cap='space.export'
            if method=='POST' and suffix in ('/api/query','/api/query-range'):cap='space.query'
            if cap is None:raise PermissionError()
            artifact(kind+':'+m[2],cap)
            # The directory/id record and model must both bind to the same scope.
            return {'principal':principal}
        if method in ('GET','HEAD'):
            if path=='/api/build-stages':
                wanted=q.get('space_id');space(wanted,'build.run');artifact('candidate:'+str(q.get('candidate_id','')),'build.run',wanted)
                return {'principal':principal}
            if path=='/api/ontologies':
                return {'principal':principal}
            if re.fullmatch(r'/api/ontologies/[^/]+/[^/]+',path):return {'principal':principal}
            caps={'/api/publications':'space.preview','/api/selection':'space.preview',
                '/api/workspace-model':'space.preview','/api/workflow':'space.preview',
                '/api/builds':'build.run','/api/inputs':'data.manage','/api/artifacts':'data.manage',
                '/api/batches':'data.manage','/api/ledger':'association.edit'}
            if path in caps:
                wanted=q.get('space_id');space(wanted,caps[path])
                if path in ('/api/selection','/api/workspace-model'):selected(wanted,caps[path])
                return {'principal':principal}
            if path in ('/api/artifact-control','/api/artifact-impact'):
                value=q.get('artifact','');kind=value.split(':')[0]
                cap={'input':'data.manage','candidate':'build.run','publication':'publication.manage'}.get(kind)
                if not cap:raise PermissionError()
                space(q.get('space_id'),cap);artifact(value,cap,q.get('space_id'))
                return {'principal':principal}
            m=re.fullmatch(r'/api/inputs/([^/]+)',path)
            if m:artifact('input:'+m[1],'data.manage',q.get('space_id'));return {'principal':principal}
            m=re.fullmatch(r'/api/inputs/([^/]+)/preflight',path)
            if m:artifact('input:'+m[1],'data.manage',q.get('space_id'));return {'principal':principal}
            m=re.fullmatch(r'/api/batches/([^/]+)',path)
            if m:batch(m[1],q.get('space_id'),'data.manage');return {'principal':principal}
        if method=='POST':
            if path=='/api/view-derivations':
                wanted=body.get('space_id');space(wanted,'build.run')
                artifact('candidate:'+str(body.get('candidate_id','')),'build.run',wanted)
                previous=json.loads((self.jobs.root/body['candidate_id']/'job.json').read_bytes())
                artifact('input:'+str(previous.get('input_id','')),'data.manage',wanted)
                if previous.get('frozen_model'):artifact('candidate:'+previous['frozen_model']['job_id'],'build.run',wanted)
                return {'principal':principal}
            if path=='/api/build-retries':
                wanted=body.get('space_id');space(wanted,'build.run')
                artifact('candidate:'+str(body.get('retry_of','')),'build.run',wanted)
                previous=json.loads((self.jobs.root/body['retry_of']/'job.json').read_bytes())
                artifact('input:'+str(previous.get('input_id','')),'data.manage',wanted)
                return {'principal':principal}
            if re.fullmatch(r'/api/ontologies/[^/]+/[^/]+/validate',path):return {'principal':principal}
            caps={'/api/ledger':'association.edit','/api/business-candidates':'association.edit',
                '/api/relation-candidates':'association.edit','/api/semantic-candidates':'association.edit',
                '/api/selection':'build.run','/api/candidate-comparisons':'build.run','/api/candidate-reviews':'build.run',
                '/api/publication-comparisons':'space.preview','/api/publications':'publication.manage',
                '/api/inputs':'data.manage','/api/batches':'data.manage','/api/builds':'build.run'}
            if path in caps:
                wanted=references(caps[path])
                if path in ('/api/selection','/api/candidate-comparisons','/api/candidate-reviews','/api/publications'):
                    selected(wanted,caps[path])
                if body.get('batch_id'):batch(body['batch_id'],wanted,'data.manage')
                return {'principal':principal}
            if path=='/api/artifact-control/transitions':
                value=body.get('artifact','');cap={'input':'data.manage','candidate':'build.run','publication':'publication.manage'}.get(value.split(':')[0])
                if not cap:raise PermissionError()
                space(body.get('space_id'),cap);artifact(value,cap,body.get('space_id'))
                if body.get('replacement_publication_id'):artifact('publication:'+body['replacement_publication_id'],'publication.manage',body.get('space_id'))
                return {'principal':principal}
            m=re.fullmatch(r'/api/inputs/([^/]+)/preflight',path)
            if m:artifact('input:'+m[1],'data.manage',q.get('space_id'));return {'principal':principal}
            m=re.fullmatch(r'/api/batches/([^/]+)/transitions',path)
            if m:references('data.manage');batch(m[1],body.get('space_id'),'data.manage');return {'principal':principal}
        # New routes, unscoped default model, root static aliases, project creation,
        # global ontology registration and member writes cannot inherit a space grant.
        raise PermissionError()

    async def dispatch(self, request, call_next):
        path=request.url.path
        def deny(status,detail):return JSONResponse({'detail':detail},status_code=status,headers={'Cache-Control':'no-store'})
        try:
            # Starlette already decoded the ASGI path. Reject ambiguous encodings,
            # doubled separators and dot segments before inner routing/static fallback.
            if '\\' in path or '//' in path or any(p in ('.','..') for p in path.split('/')) or unquote(path)!=path:
                return deny(403,'space_access_denied')
            if path=='/s2s' or path.startswith('/s2s/'):
                if self.consumer is None:return deny(404,'consumer_not_configured')
                return await self.consumer.dispatch(request)
            # Public exceptions are exact auth routes. Prefix exemptions could let
            # an unhandled auth-looking path fall through to the inner static mount.
            if path in ('/auth/login','/auth/callback','/auth/logout','/api/auth/config','/api/auth/session','/api/subscription','/api/webhooks/vxture','/') or path.startswith('/workbench/'):
                return await call_next(request)
            if any(len(request.query_params.getlist(k))>1 for k in request.query_params):return deny(403,'space_access_denied')
            rpsid=request.cookies.get(self.rp.config.cookie_name)
            session,_=await run_in_threadpool(self.rp.resolve,rpsid,active=False,require_access=True)
            if session is None:return deny(401,'authentication_required')
            if request.method not in ('GET','HEAD'):
                if (request.headers.get('origin')!=self.rp.config.origin or request.headers.get('sec-fetch-site')=='cross-site'
                        or not self.rp.csrf_matches(rpsid,request.headers.get('x-cospace-csrf'))):return deny(403,'csrf_rejected')
            await run_in_threadpool(self.require_subscription,session)
            if path=='/api/input-uploads' and request.method in ('GET','POST'):
                revision,policy=await run_in_threadpool(self.policies.load)
                context=await run_in_threadpool(self.authorize,request,session,policy,{})
                if self.jobs.inputs is None:return deny(503,'input_catalog_not_configured')
                if request.method=='GET':return JSONResponse(upload_capabilities(),headers={'Cache-Control':'no-store'})
                if set(request.query_params)!={'space_id','label'}:return deny(422,'upload_metadata_invalid')
                upload_metadata(request.query_params.get('space_id'),request.query_params.get('label'))
                if request.headers.get('content-type','').split(';')[0]!='application/zip':return deny(415,'upload_zip_required')
                length=request.headers.get('content-length')
                if length is not None and (not length.isdigit() or not 0<int(length)<=MAX_UPLOAD):return deny(413,'upload_size_budget')
                import tempfile
                from pathlib import Path
                staging=self.jobs.inputs.root/'.upload-staging';staging.mkdir(exist_ok=True)
                with tempfile.TemporaryDirectory(dir=staging,prefix='receive-') as temporary:
                    upload=Path(temporary)/'package.zip';received=0
                    with upload.open('xb') as stream:
                        async for chunk in request.stream():
                            received+=len(chunk)
                            if received>MAX_UPLOAD:return deny(413,'upload_size_budget')
                            await run_in_threadpool(stream.write,chunk)
                    # Upload may outlast a session/policy confirmation. Recheck before commit.
                    current,_=await run_in_threadpool(self.rp.resolve,rpsid,active=False,require_access=True)
                    if current is None:return deny(401,'authentication_required')
                    await run_in_threadpool(self.require_subscription,current)
                    revision,policy=await run_in_threadpool(self.policies.load)
                    context=await run_in_threadpool(self.authorize,request,current,policy,{})
                    try:result=await run_in_threadpool(InputUploads(self.jobs.inputs).register,upload,
                        request.query_params['space_id'],request.query_params['label'],context['principal'].subject)
                    except ImportError:return deny(503,'registration_adapter_unavailable')
                return JSONResponse(result,status_code=201 if result['created'] else 200,headers={'Cache-Control':'no-store'})
            raw=await request.body() if request.method not in ('GET','HEAD') else b''
            if len(raw)>1_048_576:return deny(413,'request_too_large')
            def unique_pairs(pairs):
                value={}
                for key,item in pairs:
                    if key in value:raise ValueError('duplicate_body_key')
                    value[key]=item
                return value
            body=json.loads(raw,object_pairs_hook=unique_pairs) if raw else {}
            if not isinstance(body,dict):return deny(403,'space_access_denied')
            revision,policy=await run_in_threadpool(self.policies.load)
            context=await run_in_threadpool(self.authorize,request,session,policy,body)
            request.state.platform_principal=context['principal'];request.state.policy_revision=revision
            shared=getattr(self.jobs,'ontology_store',None)
            rules=WorkspaceOntologies(shared.root if shared else self.jobs.root.parent/'preview-ontologies',context['principal'])
            request.state.ontology_store=rules
            if path.startswith('/api/ontology-authoring'):
                try:
                    if path=='/api/ontology-authoring' and request.method in ('GET','HEAD'):
                        result={'profile':'cospace.ontology-authoring/0.1','workspace_id':context['principal'].workspace_id,
                                'can_edit':context['principal'].workspace_owner,'drafts':rules.drafts()}
                    elif path=='/api/ontology-authoring/drafts' and request.method=='POST':
                        result=await run_in_threadpool(rules.save,DraftChange.model_validate(body),context['principal'].subject)
                    elif path=='/api/ontology-authoring/validate' and request.method=='POST':
                        if set(body)!={'definition'}:return deny(422,'ontology_validation_invalid_request')
                        result=rules.validate(body['definition'])
                    elif path=='/api/ontology-authoring/seal' and request.method=='POST':
                        result=await run_in_threadpool(rules.seal,SealDraft.model_validate(body),context['principal'].subject)
                    else:return deny(404,'ontology_authoring_route_not_found')
                except ValidationError:return deny(422,'ontology_authoring_invalid_request')
                except (ValueError,TypeError) as exc:return deny(409,str(exc))
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            rgbd_path=re.fullmatch(r'/api/inputs/([^/]+)/rgbd-preview(/frame)?',path)
            if rgbd_path:
                if self.jobs.inputs is None:return deny(503,'input_catalog_not_configured')
                is_frame=bool(rgbd_path[2]);expected={'space_id','frame_index'} if is_frame else {'space_id'}
                if set(request.query_params)!=expected:return deny(422,'rgbd_preview_invalid_request')
                params=(self.jobs.inputs,rgbd_path[1],request.query_params['space_id'])
                if is_frame:
                    raw_index=request.query_params['frame_index']
                    if not re.fullmatch(r'0|[1-9][0-9]{0,2}',raw_index):return deny(422,'rgbd_preview_invalid_frame')
                    result=await run_in_threadpool(rgbd_frame,*params,int(raw_index))
                else:result=await run_in_threadpool(rgbd_directory,*params)
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            if path=='/api/build-preview':
                if set(request.query_params)!={'space_id','candidate_id','kind'}:return deny(422,'build_preview_invalid_request')
                result=await run_in_threadpool(build_preview,self.jobs,request.query_params['space_id'],request.query_params['candidate_id'],request.query_params['kind'])
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            if path=='/api/build-process':
                if set(request.query_params)!={'space_id','candidate_id'} or len(request.query_params.multi_items())!=2:
                    return deny(422,'build_process_invalid_request')
                result=await run_in_threadpool(read_process,self.jobs,request.query_params['space_id'],request.query_params['candidate_id'])
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            if path=='/api/artifact-control/transitions':
                from packages.lifecycle.preview_control import ControlChange
                from packages.service.preview_publications import PreviewPublications
                try:change=ControlChange.model_validate(body)
                except ValidationError:return deny(422,'invalid_control_request')
                try:result=await run_in_threadpool(self.jobs.controls.change,PreviewPublications(self.jobs),change,context['principal'].subject)
                except ValueError as exc:return deny(409,str(exc))
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            metadata_path=re.fullmatch(r'/api/inputs/([^/]+)/(description|facts|preview|coordinates)',path)
            if metadata_path:
                if self.jobs.inputs is None:return deny(503,'input_catalog_not_configured')
                identity=metadata_path[1]
                wanted=body.get('space_id') if request.method=='POST' else request.query_params.get('space_id')
                store=InputDescriptions(self.jobs.inputs)
                if metadata_path[2]=='coordinates':
                    coords=InputCoordinates(self.jobs.inputs)
                    if request.method=='POST':
                        try:change=CoordinateChange.model_validate(body)
                        except ValidationError:return deny(422,'invalid_coordinate_change')
                        try:result=await run_in_threadpool(coords.change,identity,change,context['principal'].subject)
                        except ValueError as exc:return deny(409,str(exc))
                    else:
                        if set(request.query_params)!={'space_id'}:return deny(422,'invalid_coordinate_request')
                        result=await run_in_threadpool(coords.read,identity,wanted)
                elif metadata_path[2]=='preview':
                    if set(request.query_params)!={'space_id'}:return deny(422,'input_preview_invalid_request')
                    result=await run_in_threadpool(input_preview,self.jobs.inputs,identity,wanted)
                elif metadata_path[2]=='facts':
                    result=await run_in_threadpool(facts,self.jobs.inputs,identity,wanted)
                elif request.method=='POST':
                    try:change=DescriptionChange.model_validate(body)
                    except ValidationError:return deny(422,'invalid_input_description')
                    result=await run_in_threadpool(store.change,identity,change,context['principal'].subject)
                else:result=await run_in_threadpool(store.read,identity,wanted)
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            if path=='/api/inputs' and request.method in ('GET','HEAD'):
                if self.jobs.inputs is None:return deny(503,'input_catalog_not_configured')
                wanted=request.query_params.get('space_id')
                def entries():
                    store=InputDescriptions(self.jobs.inputs)
                    records=[r for r in self.jobs.inputs.list() if r.get('space_id')==wanted]
                    return [r|{'route':route(r['format']),'presentation':store.presentation(r),
                        'lifecycle_state':self.jobs.controls.read(wanted,'input:'+r['id'])['lifecycle_state']} for r in records]
                return JSONResponse({'inputs':await run_in_threadpool(entries),'selection_required':True},headers={'Cache-Control':'no-store'})
            if path=='/api/workspace-scenes':
                if request.method in ('GET','HEAD'):
                    return JSONResponse(context['workspace_context'],headers={'Cache-Control':'no-store'})
                try:change=CreateScene.model_validate(body)
                except ValidationError:return deny(422,'invalid_workspace_scene_request')
                try:result=await run_in_threadpool(self.workspace_scenes.create,context['principal'],change)
                except (OSError,sqlite3.Error):return deny(503,'workspace_scene_storage_unavailable_retry_same_request')
                return JSONResponse(result,status_code=201 if result['created'] else 200,headers={'Cache-Control':'no-store'})
            check_path=re.fullmatch(r'/api/inputs/([^/]+)/preflight',path)
            if check_path:
                store=PreflightRecords(self.jobs.inputs)
                if request.method=='POST':
                    from packages.data.preview_preflight import preflight
                    fingerprint=await run_in_threadpool(store.fingerprint,check_path[1])
                    try:report=await run_in_threadpool(preflight,self.jobs.inputs,check_path[1])
                    except ImportError:return deny(503,'registration_adapter_unavailable')
                    try:report=await run_in_threadpool(store.save,check_path[1],report,context['principal'].subject,fingerprint)
                    except ValueError:return deny(409,'preflight_registration_changed')
                    return JSONResponse(report,headers={'Cache-Control':'no-store'})
                report=await run_in_threadpool(store.latest,check_path[1])
                return JSONResponse({'last_check':report,'current_files_checked':False},headers={'Cache-Control':'no-store'})
            if path=='/api/workflow':
                from packages.service.preview_workflow import workflow
                from packages.service.preview_publications import PreviewPublications
                identity=request.query_params.get('space_id')
                caps=policy.capabilities(context['principal'],identity)
                try:
                    prep=None
                    if 'data.manage' in caps:
                        scoped_sources=await run_in_threadpool(self.workspace_scenes.scoped_sources,context['principal'])
                        prep=await run_in_threadpool(preparation,self.jobs,scoped_sources,identity,request.query_params.get('input_id'),request.query_params.get('batch_id'))
                    result=await run_in_threadpool(workflow,PreviewPublications(self.jobs),identity,
                        request.query_params.get('job_id'),request.query_params.get('publication_id'),prep)
                except PermissionError:raise
                except sqlite3.Error:return deny(503,'workflow_records_unavailable')
                except (ValueError,OSError,KeyError,TypeError):return deny(409,'workflow_unavailable_refresh_required')
                result['business_authorized']=True
                required={'data':'data.manage','build':'build.run','ontology':'space.preview','association':'association.edit','delivery':'space.preview','space':'space.preview'}
                for stage in result['stages']:
                    stage['action']['allowed']=required[stage['action']['module']] in caps
                result['next_action']['allowed']=required[result['next_action']['module']] in caps
                summary=result['summary']
                summary['primary_action']['allowed']=required[summary['primary_action']['module']] in caps
                if summary['work']:summary['work']['action']['allowed']=required[summary['work']['action']['module']] in caps
                if 'build.run' not in caps:
                    summary['work']=None;summary['candidate_ref']=None;summary['tracked_job']=None
                    result['candidate_ref']=None;result['selection_status']='not_disclosed'
                    result['counts']={k:v for k,v in result['counts'].items() if k in ('publication','offline_package')}
                    for stage in result['stages']:
                        stage['action']['values']={k:v for k,v in stage['action']['values'].items() if k not in ('job','input','batch')}
                        if stage['id'] in ('data','build','ontology','association'):
                            stage['detail']='需具备对应空间操作权限。';stage['action']['values']={'space':identity}
                    result['next_action']['values']={k:v for k,v in result['next_action']['values'].items() if k not in ('job','input','batch')}
                    summary['primary_action']['values']={k:v for k,v in summary['primary_action']['values'].items() if k not in ('job','input','batch')}
                    if summary['primary_action']['allowed'] is False:
                        summary['primary_action']={'module':'delivery','label':'查看固定发布','values':{'space':identity},'allowed':True}
                if result.get('preparation'):
                    a=result['preparation']['next_action']
                    a['allowed']=('space.manage' if a['values'].get('tab')=='sources' else required[a['module']]) in caps
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            if path in ('/api/source-settings','/api/registration-sources'):
                sources=await run_in_threadpool(self.workspace_scenes.scoped_sources,context['principal'])
                identity=request.query_params.get('space_id') if request.method in ('GET','HEAD') else body.get('space_id')
                if request.method=='POST':
                    change=SourceChange.model_validate(body)
                    saved=await run_in_threadpool(sources.change,change,context['principal'].subject)
                else:saved=await run_in_threadpool(sources.read,identity)
                can_manage='space.manage' in policy.capabilities(context['principal'],identity)
                result=sources.view(identity,can_manage,saved)
                if path=='/api/registration-sources':
                    result={'sources':result['sources'],'configuration':{'scope':'space','revision':saved['revision'],
                        'enabled_count':len(result['sources']),'reload_policy':'per_request'}}
                    result['sources']=[s|{'route':route(s['format'])} for s in result['sources']]
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            if path=='/api/inputs' and request.method=='POST':
                sources=await run_in_threadpool(self.workspace_scenes.scoped_sources,context['principal'])
                from experiments.scripts.serve_nyu_flow_preview import RegistrationRequest
                change=RegistrationRequest.model_validate(body)
                saved=await run_in_threadpool(sources.read,change.space_id)
                allowed=sources.effective(saved)
                if change.source_id not in allowed:return deny(409,'registration_source_not_allowed')
                if self.registration is None:return deny(503,'input_catalog_not_configured')
                # A fresh registration wrapper prevents cross-request mutable source
                # maps while sharing its duplicate-registration lock.
                registration=PreviewRegistration(self.jobs.inputs,allowed,{
                    'source_id':change.source_id,'settings_revision':saved['revision'],
                    'catalog_sha256':sources.catalog_sha256,'actor':context['principal'].subject})
                registration.lock=self.registration.lock
                try:result=await run_in_threadpool(registration.register,change.source_id,change.label,change.space_id)
                except ImportError:return deny(503,'registration_adapter_unavailable')
                except (ValueError,OSError,KeyError,TypeError,IndexError):return deny(409,'registration_validation_failed')
                return JSONResponse(result,status_code=201 if result['created'] else 200,headers={'Cache-Control':'no-store'})
            if path=='/api/space-settings':
                identity=request.query_params.get('space_id') if request.method in ('GET','HEAD') else body.get('space_id')
                record=self.directory.read('space',identity)
                if request.method=='POST':
                    change=SpaceSettingsChange.model_validate(body)
                    saved=await run_in_threadpool(self.directory.settings.change,change,context['principal'].subject,record)
                else:
                    saved=await run_in_threadpool(self.directory.settings.read,identity)
                # Use one settings snapshot for both fields and revision. Another
                # manager may save after this transaction has committed.
                record=record|{key:saved[key] for key in ('name','description') if key in saved}
                caps=sorted(policy.capabilities(context['principal'],identity))
                payload={'space':record,'revision':saved['revision'],'can_manage':'space.manage' in caps,
                         'editable_fields':['name','description'],
                         'history':saved['history'] if 'space.manage' in caps else []}
                return JSONResponse(payload,headers={'Cache-Control':'no-store'})
            if request.method in ('GET','HEAD') and path in ('/api/projects','/api/spaces'):
                from packages.service.preview_publications import PreviewPublications
                visible=context['visible'];pubs=PreviewPublications(self.jobs)
                if path=='/api/projects':
                    result={'projects':[self.directory.read('project',p) for p in sorted({s['project_id'] for s in visible})]}
                else:
                    values=[]
                    for record in visible:
                        # Only read metadata for this authorized space, before lifecycle
                        # inspection; unassigned/foreign releases never reach the renderer.
                        related=[]
                        for p in sorted(pubs.root.glob('*/publication.json')):
                            saved=json.loads(p.read_bytes())
                            if saved.get('space_id')!=record['id']:continue
                            if saved.get('project_id')!=record['project_id']:raise PermissionError()
                            status=pubs.distribution(saved['id'])
                            related.append(saved|status)
                        related.sort(key=lambda v:v['created_at'],reverse=True)
                        latest=related[0] if related else None
                        values.append(record|{'publications':related,'capabilities':sorted(policy.capabilities(context['principal'],record['id'])),
                            'publication_id':latest['id'] if latest and latest['lifecycle_state']=='active' else None,
                            'state':'no_publication' if not latest else 'preview_published' if latest['lifecycle_state']=='active' else 'distribution_paused'})
                    result={'spaces':values,'legacy_records':'unassigned','access_scope':'authorized_spaces','policy_revision':revision}
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            return await call_next(request)
        except PreviewUnavailable as exc:return deny(409,str(exc))
        except UploadRejected as exc:return deny(422,str(exc))
        except CoordinatesConflict as exc:return deny(409,str(exc))
        except CoordinatesUnavailable:return deny(503,'input_coordinates_unavailable')
        except DescriptionConflict:return deny(409,'input_description_revision_changed')
        except DescriptionUnavailable:return deny(503,'input_descriptions_unavailable')
        except FactsUnavailable as exc:return deny(409,str(exc))
        except WorkspaceScenesConflict as exc:return deny(409,str(exc))
        except WorkspaceScenesUnavailable:return deny(503,'workspace_scene_configuration_unavailable')
        except SettingsConflict:return deny(409,'space_settings_revision_changed')
        except SettingsUnavailable:return deny(503,'space_settings_unavailable')
        except SourcesConflict as exc:return deny(409,str(exc))
        except SourcesUnavailable:return deny(503,'source_settings_unavailable')
        except PreflightUnavailable:return deny(503,'preflight_records_unavailable')
        except SubscriptionDenied:return deny(403,'subscription_required')
        except SubscriptionUnavailable:return deny(503,'subscription_unavailable')
        except IdentityUnavailable:return deny(503,'platform_or_policy_unavailable')
        except IdentityRejected:return deny(401,'access_credential_unavailable')
        except (PermissionError,ValueError,TypeError,KeyError,OSError):return deny(403,'space_access_denied')
