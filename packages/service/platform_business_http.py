from packages.infrastructure.platform_rp import APP_ROUTES
"""Explicit deny-by-default authorization before the engineering business ASGI app."""
import json
import re
import sqlite3
import zipfile
from pydantic import ValidationError
from packages.lifecycle.workspace_scenes import WorkspaceScenes,CreateScene,WorkspaceScenesConflict,WorkspaceScenesUnavailable
from urllib.parse import unquote,quote
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from packages.infrastructure.platform_identity import PlatformPrincipal, IdentityRejected, IdentityUnavailable
from packages.infrastructure.platform_subscription import SubscriptionDenied, SubscriptionUnavailable, ApplicationAccessDenied
from packages.service.platform_resource_access import PlatformResourceAccess
from packages.lifecycle.space_settings import SpaceSettingsChange, SettingsConflict, SettingsUnavailable
from packages.data.space_sources import SpaceSources, SourceChange, SourcesConflict, SourcesUnavailable
from packages.data.preview_registration import PreviewRegistration
from packages.data.preflight_records import PreflightRecords, PreflightUnavailable, PreflightHistoryQuery
from packages.data.input_descriptions import InputDescriptions, DescriptionChange, DescriptionConflict, DescriptionUnavailable
from packages.data.input_coordinates import InputCoordinates, CoordinateChange, CoordinatesConflict, CoordinatesUnavailable
from packages.data.input_routes import route
from packages.data.input_facts import facts, FactsUnavailable
from packages.data.input_preview import preview as input_preview,PreviewUnavailable
from packages.data.scene_pointcloud_workspace import ScenePointcloudWorkspace,ComposeRegion,SceneCloudUnavailable,SceneCloudConflict,SceneCloudAuthorizationPending
from packages.data.ifc_workspace import IfcWorkspace
from packages.data.scene_attachments import SceneAttachments,AttachmentRejected,MAX_BYTES as MAX_ATTACHMENT_BYTES,metadata as attachment_metadata
from packages.data.rgbd_input_preview import directory as rgbd_directory, frame as rgbd_frame
from packages.construction.build_preview import preview as build_preview
from packages.construction.build_process import read_process
from packages.service.space_preparation import preparation
from packages.data.input_uploads import InputUploads,UploadRejected,MAX_UPLOAD,capabilities as upload_capabilities,metadata as upload_metadata
from packages.ontology.workspace_authoring import WorkspaceOntologies,DraftChange,SealDraft
from packages.ontology.scene_usage import usage as scene_ontology_usage, UsageQuery
from packages.service.public_errors import public_error
from packages.service.service_recipients import ServiceRecipients, RecipientChange, RecipientConflict, RecipientsUnavailable
from packages.service.scene_overview import overview as scene_overview
from packages.service.amap_gateway import AmapGateway
from packages.service.globe_runtime import GlobeRuntime
from packages.data.workspace_catalog import catalog as workspace_catalog, CatalogQuery, CatalogUnavailable


DATA_MANAGE='data.manage'
SPACE_PREVIEW='space.preview'

SELECTION_ROUTE='/api/selection'
PUBLICATIONS_ROUTE='/api/publications'
INPUTS_ROUTE='/api/inputs'
PUBLICATION_MANAGE='publication.manage'


class BusinessAccess:
    def __init__(self, rp, policies, directory, jobs, registration_sources=None,workspace_config=None,consumer_config=None,subscriptions=None,scene_pointcloud_config=None,scene_ifc_config=None):
        self.rp,self.policies,self.directory,self.jobs=rp,policies,directory,jobs
        self.subscriptions=subscriptions
        self.amap=AmapGateway.from_env()
        self.globe=GlobeRuntime.from_env()
        self.scene_pointclouds=ScenePointcloudWorkspace(jobs.inputs,scene_pointcloud_config) if jobs.inputs else None
        self.scene_ifc=IfcWorkspace(directory,jobs,scene_ifc_config)
        self.attachments=SceneAttachments(jobs.inputs) if jobs.inputs else None
        self.sources=SpaceSources(directory.root,registration_sources or {})
        self.recipients=ServiceRecipients(directory.root)
        self.workspace_scenes=WorkspaceScenes(directory,policies,self.sources,workspace_config,
            platform_access=subscriptions is not None)
        self.registration=PreviewRegistration(jobs.inputs,{}) if jobs.inputs else None
        self.consumer=None
        from packages.service.service_monitor import ServiceMonitor
        self.service_monitor=ServiceMonitor(jobs.root)
        if consumer_config is not None:
            from packages.service.online_consumer import OnlineConsumer
            self.consumer=OnlineConsumer(rp,policies,jobs,consumer_config,subscriptions=subscriptions,monitor=self.service_monitor)

    def require_subscription(self,session):
        if self.subscriptions is not None:
            principal=self.rp.verifier.verify(session['access_token'])
            return self.subscriptions.require(principal,session['access_token'],ui=True)

    def authorize(self, request, session, policy, body):
        principal=self.rp.verifier.verify(session['access_token'])
        access=PlatformResourceAccess(self.directory,self.jobs,policy)
        path=request.url.path; method=request.method; q=request.query_params
        if path=='/api/service-recipients' and method in ('GET','POST') or re.fullmatch(r'/api/service-recipients/agent-[a-f0-9]{32}',path) and method=='PATCH':
            return {'principal':principal}
        if path=='/api/service-monitor' and method=='GET':
            access.space(principal,q.get('space_id'),PUBLICATION_MANAGE)
            return {'principal':principal}
        if path=='/api/ontology-usage' and method in ('GET','HEAD'):
            access.space(principal,q.get('space_id'),DATA_MANAGE)
            access.space(principal,q.get('space_id'),SPACE_PREVIEW)
            return {'principal':principal}
        if path=='/api/data-catalog' and method in ('GET','HEAD'):
            if q.get('space_id'):access.space(principal,q['space_id'],DATA_MANAGE)
            return {'principal':principal}
        if path=='/api/workspace-scenes' and method in ('GET','HEAD','POST'):
            context=self.workspace_scenes.context(principal)
            if method=='POST' and not context['can_create']:raise PermissionError()
            return {'principal':principal,'workspace_context':context}
        def space(identity,cap=SPACE_PREVIEW):
            return access.space(principal,identity,cap)
        def artifact(value,cap=SPACE_PREVIEW,wanted=None):
            return access.artifact(principal,value,cap,requested_space=wanted)
        def references(cap):
            wanted=body.get('space_id');space(wanted,cap)
            for field in ('candidate_id','base_candidate_id'):
                if body.get(field):artifact('candidate:'+body[field],cap,wanted)
            for field in ('base_publication_id','target_publication_id'):
                if body.get(field):artifact('publication:'+body[field],cap,wanted)
            for value in body.get('input_ids') or []:artifact('input:'+value,cap,wanted)
            if body.get('input_id'):artifact('input:'+body['input_id'],DATA_MANAGE,wanted)
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
            space(q.get('space_id'),DATA_MANAGE);return {'principal':principal}
        if (path=='/api/scene-attachments' or re.fullmatch(r'/api/scene-attachments/attachment-[a-f0-9]{16}',path)) and method in ('GET','HEAD','POST'):
            space(q.get('space_id'),DATA_MANAGE);return {'principal':principal}
        if path in ('/api/scene-ifc','/api/scene-ifc/element') and method in ('GET','HEAD'):
            space(q.get('space_id'),'association.edit');return {'principal':principal}
        if ((path=='/api/scene-pointclouds' or re.fullmatch(r'/api/scene-pointclouds/(tiles/t[0-9]{5}/[0-2]|compositions/compose-[a-f0-9]{24})',path)) and method in ('GET','HEAD')
                or (path=='/api/scene-pointclouds/compositions' or re.fullmatch(r'/api/scene-pointclouds/compositions/compose-[a-f0-9]{24}/register',path)) and method=='POST'):
            space(body.get('space_id') if method=='POST' else q.get('space_id'),DATA_MANAGE)
            return {'principal':principal}
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
            wanted=q.get('space_id');space(wanted,DATA_MANAGE);artifact('input:'+rgbd_path[1],DATA_MANAGE,wanted)
            return {'principal':principal}
        metadata_path=re.fullmatch(r'/api/inputs/([^/]+)/(description|facts|preview|coordinates)',path)
        if metadata_path and (method in ('GET','HEAD') or method=='POST' and metadata_path[2] in ('description','coordinates')):
            wanted=body.get('space_id') if method=='POST' else q.get('space_id')
            space(wanted,DATA_MANAGE);artifact('input:'+metadata_path[1],DATA_MANAGE,wanted)
            return {'principal':principal}
        if path in ('/api/source-settings','/api/registration-sources') and method in ('GET','HEAD'):
            space(q.get('space_id'),DATA_MANAGE);return {'principal':principal}
        if path=='/api/source-settings' and method=='POST':
            space(body.get('space_id'),'space.manage');return {'principal':principal}
        if path=='/api/scene-overview' and method in ('GET','HEAD'):
            space(q.get('space_id'));return {'principal':principal}
        if path=='/api/workflow' and method in ('GET','HEAD'):
            space(q.get('space_id'))
            if q.get('input_id'):artifact('input:'+q['input_id'],DATA_MANAGE,q.get('space_id'))
            if q.get('job_id'):artifact('candidate:'+q['job_id'],'build.run',q.get('space_id'))
            if q.get('publication_id'):artifact('publication:'+q['publication_id'],SPACE_PREVIEW,q.get('space_id'))
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
                if kind=='publication' and suffix=='/api/provenance':
                    if q:raise PermissionError()
                    artifact(kind+':'+m[2],DATA_MANAGE)
                    artifact(kind+':'+m[2],SPACE_PREVIEW)
                    return {'principal':principal}
                if suffix in ('/','/index.html','/human.ply','/views.js','/model.json','/objects.json','/ontology.json','/business.json','/relations.json',
                              '/api/preview','/api/thumbnail','/api/objects','/api/checklist','/api/lineage') or re.fullmatch(r'/api/objects/[^/]+',suffix):cap=SPACE_PREVIEW
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
            caps={PUBLICATIONS_ROUTE:SPACE_PREVIEW,SELECTION_ROUTE:SPACE_PREVIEW,
                '/api/workspace-model':SPACE_PREVIEW,'/api/workflow':SPACE_PREVIEW,
                '/api/builds':'build.run',INPUTS_ROUTE:DATA_MANAGE,'/api/artifacts':DATA_MANAGE,
                '/api/batches':DATA_MANAGE,'/api/ledger':'association.edit'}
            if path in caps:
                wanted=q.get('space_id');space(wanted,caps[path])
                if path in (SELECTION_ROUTE,'/api/workspace-model'):selected(wanted,caps[path])
                return {'principal':principal}
            if path in ('/api/artifact-control','/api/artifact-impact'):
                value=q.get('artifact','');kind=value.split(':')[0]
                cap={'input':DATA_MANAGE,'candidate':'build.run','publication':PUBLICATION_MANAGE}.get(kind)
                if not cap:raise PermissionError()
                space(q.get('space_id'),cap);artifact(value,cap,q.get('space_id'))
                return {'principal':principal}
            m=re.fullmatch(r'/api/inputs/([^/]+)',path)
            if m:artifact('input:'+m[1],DATA_MANAGE,q.get('space_id'));return {'principal':principal}
            m=re.fullmatch(r'/api/inputs/([^/]+)/preflight(?:/history)?',path)
            if m:artifact('input:'+m[1],DATA_MANAGE,q.get('space_id'));return {'principal':principal}
            m=re.fullmatch(r'/api/batches/([^/]+)',path)
            if m:batch(m[1],q.get('space_id'),DATA_MANAGE);return {'principal':principal}
        if method=='POST':
            if path=='/api/view-derivations':
                wanted=body.get('space_id');space(wanted,'build.run')
                artifact('candidate:'+str(body.get('candidate_id','')),'build.run',wanted)
                previous=json.loads((self.jobs.root/body['candidate_id']/'job.json').read_bytes())
                artifact('input:'+str(previous.get('input_id','')),DATA_MANAGE,wanted)
                if previous.get('frozen_model'):artifact('candidate:'+previous['frozen_model']['job_id'],'build.run',wanted)
                return {'principal':principal}
            if path=='/api/build-info':
                wanted=body.get('space_id');space(wanted,'build.run')
                artifact('candidate:'+str(body.get('candidate_id','')),'build.run',wanted)
                return {'principal':principal}
            if path=='/api/build-retries':
                wanted=body.get('space_id');space(wanted,'build.run')
                artifact('candidate:'+str(body.get('retry_of','')),'build.run',wanted)
                previous=json.loads((self.jobs.root/body['retry_of']/'job.json').read_bytes())
                artifact('input:'+str(previous.get('input_id','')),DATA_MANAGE,wanted)
                return {'principal':principal}
            if re.fullmatch(r'/api/ontologies/[^/]+/[^/]+/validate',path):return {'principal':principal}
            caps={'/api/ledger':'association.edit','/api/business-candidates':'association.edit',
                '/api/relation-candidates':'association.edit','/api/semantic-candidates':'association.edit',
                SELECTION_ROUTE:'build.run','/api/candidate-comparisons':'build.run','/api/candidate-reviews':'build.run',
                '/api/publication-comparisons':SPACE_PREVIEW,PUBLICATIONS_ROUTE:PUBLICATION_MANAGE,
                INPUTS_ROUTE:DATA_MANAGE,'/api/batches':DATA_MANAGE,'/api/builds':'build.run'}
            if path in caps:
                wanted=references(caps[path])
                if path in (SELECTION_ROUTE,'/api/candidate-comparisons','/api/candidate-reviews',PUBLICATIONS_ROUTE):
                    selected(wanted,caps[path])
                if body.get('batch_id'):batch(body['batch_id'],wanted,DATA_MANAGE)
                return {'principal':principal}
            if path=='/api/artifact-control/transitions':
                value=body.get('artifact','');cap={'input':DATA_MANAGE,'candidate':'build.run','publication':PUBLICATION_MANAGE}.get(value.split(':')[0])
                if not cap:raise PermissionError()
                space(body.get('space_id'),cap);artifact(value,cap,body.get('space_id'))
                if body.get('replacement_publication_id'):artifact('publication:'+body['replacement_publication_id'],PUBLICATION_MANAGE,body.get('space_id'))
                return {'principal':principal}
            m=re.fullmatch(r'/api/inputs/([^/]+)/preflight',path)
            if m:artifact('input:'+m[1],DATA_MANAGE,q.get('space_id'));return {'principal':principal}
            m=re.fullmatch(r'/api/batches/([^/]+)/transitions',path)
            if m:references(DATA_MANAGE);batch(m[1],body.get('space_id'),DATA_MANAGE);return {'principal':principal}
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
            if path=='/workbench' or path.startswith('/workbench/') or path=='/index.html':
                return deny(404,'page_not_found')
            if path in ('/auth/login','/auth/callback','/auth/logout','/api/auth/config','/api/auth/session','/api/auth/logout','/api/subscription','/api/webhooks/vxture') or path in APP_ROUTES or path.startswith('/assets/'):
                return await call_next(request)
            if any(len(request.query_params.getlist(k))>1 for k in request.query_params):return deny(403,'space_access_denied')
            rpsid=request.cookies.get(self.rp.config.cookie_name)
            session,_=await run_in_threadpool(self.rp.resolve,rpsid,active=False,require_access=True)
            if session is None:return deny(401,'authentication_required')
            if request.method not in ('GET','HEAD'):
                if (request.headers.get('origin')!=self.rp.config.origin or request.headers.get('sec-fetch-site')=='cross-site'
                        or not self.rp.csrf_matches(rpsid,request.headers.get('x-cospace-csrf'))):return deny(403,'csrf_rejected')
            await run_in_threadpool(self.require_subscription,session)
            if path=='/api/globe/config':
                if request.method not in ('GET','HEAD') or request.query_params:return deny(403,'globe_config_request_rejected')
                return JSONResponse(self.globe.public(self.rp.config.origin),headers={'Cache-Control':'no-store'})
            if path=='/api/map/config' or path.startswith('/_AMapService/'):
                return await self.amap.dispatch(request)
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
            attachment_path=re.fullmatch(r'/api/scene-attachments/(attachment-[a-f0-9]{16})',path)
            if (path=='/api/scene-attachments' or attachment_path) and request.method in ('GET','HEAD','POST'):
                revision,policy=await run_in_threadpool(self.policies.load)
                context=await run_in_threadpool(self.authorize,request,session,policy,{})
                request.state.platform_principal=context['principal'];request.state.policy_revision=revision
                if self.attachments is None:return deny(503,'input_catalog_not_configured')
                if request.method in ('GET','HEAD'):
                    if attachment_path:
                        if set(request.query_params)!={'space_id'}:return deny(422,'attachment_request_invalid')
                        try:
                            record,raw=await run_in_threadpool(self.attachments.download,request.query_params['space_id'],attachment_path[1])
                        except (AttachmentRejected,OSError,ValueError,TypeError):return deny(409,'attachment_unavailable')
                        from fastapi.responses import Response
                        return Response(raw if request.method!='HEAD' else b'',media_type='application/octet-stream',headers={
                            'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"sandbox; default-src 'none'",
                            'Content-Disposition':"attachment; filename=reference; filename*=UTF-8''"+quote(record['name'],safe=''),
                            'Content-Length':str(len(raw))})
                    if set(request.query_params)!={'space_id'}:return deny(422,'attachment_request_invalid')
                    try:result=await run_in_threadpool(self.attachments.list,request.query_params['space_id'])
                    except (AttachmentRejected,OSError,ValueError,TypeError):return deny(409,'attachment_unavailable')
                    return JSONResponse({'profile':'cospace.scene-attachments/0.1','space_id':request.query_params['space_id'],'attachments':result},headers={'Cache-Control':'no-store'})
                if attachment_path or set(request.query_params)!={'space_id','name'}:return deny(422,'attachment_metadata_invalid')
                try:attachment_metadata(request.query_params['space_id'],request.query_params['name'])
                except AttachmentRejected:return deny(422,'attachment_metadata_invalid')
                length=request.headers.get('content-length')
                if length is not None and (not length.isdigit() or not 0<int(length)<=MAX_ATTACHMENT_BYTES):return deny(413,'attachment_size_budget')
                import tempfile
                from pathlib import Path
                staging=self.jobs.inputs.root/'.upload-staging';staging.mkdir(exist_ok=True)
                with tempfile.TemporaryDirectory(dir=staging,prefix='attachment-') as temporary:
                    upload=Path(temporary)/'original';received=0
                    with upload.open('xb') as stream:
                        async for chunk in request.stream():
                            received+=len(chunk)
                            if received>MAX_ATTACHMENT_BYTES:return deny(413,'attachment_size_budget')
                            await run_in_threadpool(stream.write,chunk)
                    current,_=await run_in_threadpool(self.rp.resolve,rpsid,active=False,require_access=True)
                    if current is None:return deny(401,'authentication_required')
                    await run_in_threadpool(self.require_subscription,current)
                    revision,policy=await run_in_threadpool(self.policies.load)
                    context=await run_in_threadpool(self.authorize,request,current,policy,{})
                    try:result=await run_in_threadpool(self.attachments.register,upload,request.query_params['space_id'],request.query_params['name'],context['principal'].subject)
                    except AttachmentRejected:return deny(409,'attachment_rejected')
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
            if path=='/api/service-recipients' or path.startswith('/api/service-recipients/'):
                if request.method=='GET':
                    if set(request.query_params)-{'space_id','offset','limit','q','morphology','purpose'}:return deny(422,'recipient_query_invalid')
                    try:
                        offset=int(request.query_params.get('offset','0'));limit=int(request.query_params.get('limit','50'))
                    except ValueError:return deny(422,'recipient_query_invalid')
                    if offset<0 or not 1<=limit<=100:return deny(422,'recipient_query_invalid')
                    if request.query_params.get('morphology','') not in ('','aerial','quadruped','wheeled','tracked','humanoid','other') or request.query_params.get('purpose','') not in ('','collect','use') or len(request.query_params.get('q',''))>160:return deny(422,'recipient_query_invalid')
                    result=await run_in_threadpool(self.recipients.list,context['principal'],policy,self.directory.list('space'),
                        space_id=request.query_params.get('space_id'),offset=offset,limit=limit,query=request.query_params.get('q',''),
                        morphology=request.query_params.get('morphology',''),purpose=request.query_params.get('purpose',''))
                    return JSONResponse(result,headers={'Cache-Control':'no-store'})
                if request.query_params:return deny(422,'recipient_query_invalid')
                try:change=RecipientChange.model_validate(body)
                except ValidationError:return deny(422,'recipient_registration_invalid')
                result=await run_in_threadpool(self.recipients.save,context['principal'],policy,self.directory.list('space'),change,
                    None if path=='/api/service-recipients' else path.rsplit('/',1)[1])
                payload={k:v for k,v in result.items() if k not in ('request_id','expected_revision','created_by')}
                return JSONResponse(payload|{'can_manage':True,'integration_state':'pending','external_identity_verified':False},status_code=201 if request.method=='POST' else 200,headers={'Cache-Control':'no-store'})
            if path=='/api/service-monitor':
                if set(request.query_params)!={'space_id'}:return deny(422,'monitor_query_invalid')
                try:result=await run_in_threadpool(self.service_monitor.snapshot,context['principal'],request.query_params['space_id'])
                except (OSError,sqlite3.Error):return deny(503,'service_monitor_unavailable')
                configuration={'state':'not_configured','callers':[]}
                if self.consumer is not None:
                    try:
                        config=await run_in_threadpool(self.consumer.load)
                        callers=sorted(g.caller for g in config.grants if g.space_id==request.query_params['space_id'])
                        configuration={'state':('configured' if callers else 'not_granted') if config.audience==self.consumer.audience else 'unavailable',
                            'callers':callers if config.audience==self.consumer.audience else []}
                    except IdentityUnavailable:configuration={'state':'unavailable','callers':[]}
                from packages.service.service_assurance import assurance
                diagnosis=await run_in_threadpool(assurance,self.jobs,request.query_params['space_id'],result,configuration)
                return JSONResponse(result|{'configuration':configuration,'assurance':diagnosis},headers={'Cache-Control':'no-store'})
            if path=='/api/data-catalog':
                try:query=CatalogQuery.model_validate(dict(request.query_params))
                except ValidationError:return deny(422,'catalog_query_invalid')
                try:result=await run_in_threadpool(workspace_catalog,self.jobs,self.directory,policy,context['principal'],query)
                except CatalogUnavailable:return deny(503,'catalog_budget_exceeded')
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            if path.startswith('/api/scene-ifc'):
                try:
                    expected={'space_id'} if path=='/api/scene-ifc' else {'space_id','element_id','catalog_sha256'}
                    if set(request.query_params)!=expected:return deny(422,'ifc_invalid_request')
                    if path=='/api/scene-ifc':result=await run_in_threadpool(self.scene_ifc.directory_view,request.query_params['space_id'])
                    else:result=await run_in_threadpool(self.scene_ifc.preview,request.query_params['space_id'],request.query_params['element_id'],request.query_params['catalog_sha256'])
                    return JSONResponse(result,headers={'Cache-Control':'no-store'})
                except ValidationError:return deny(422,'ifc_invalid_request')
                except (ValueError,KeyError,OSError,TypeError,zipfile.BadZipFile):return deny(409,'ifc_evidence_unavailable')
            if path.startswith('/api/scene-pointclouds'):
                from fastapi.responses import Response
                if self.scene_pointclouds is None:return deny(503,'input_catalog_not_configured')
                try:
                    if request.method=='POST':
                        if request.query_params:return deny(422,'scene_cloud_invalid_request')
                        completing=re.fullmatch(r'/api/scene-pointclouds/compositions/(compose-[a-f0-9]{24})/register',path)
                        if completing:
                            if set(body)!={'space_id'}:return deny(422,'scene_cloud_invalid_request')
                            wanted=body['space_id']
                        else:
                            compose=ComposeRegion.model_validate(body);wanted=compose.space_id
                        def reauthorize():
                            try:
                                current,_=self.rp.resolve(rpsid,active=False,require_access=True)
                                if current is not None:self.require_subscription(current)
                            except (IdentityUnavailable,SubscriptionUnavailable):
                                raise SceneCloudAuthorizationPending() from None
                            except (IdentityRejected,SubscriptionDenied):
                                raise PermissionError() from None
                            if current is None:raise PermissionError()
                            _,fresh_policy=self.policies.load()
                            principal=self.rp.verifier.verify(current['access_token'])
                            if principal.subject!=context['principal'].subject:raise PermissionError()
                            PlatformResourceAccess(self.directory,self.jobs,fresh_policy).space(principal,wanted,DATA_MANAGE)
                        if completing:
                            result=await run_in_threadpool(self.scene_pointclouds.complete,wanted,completing[1],context['principal'].subject,reauthorize)
                        else:result=await run_in_threadpool(self.scene_pointclouds.start,compose,context['principal'].subject,reauthorize)
                        return JSONResponse(result,status_code=202,headers={'Cache-Control':'no-store'})
                    tile_path=re.fullmatch(r'/api/scene-pointclouds/tiles/(t[0-9]{5})/([0-2])',path)
                    expected={'space_id','index_sha256'} if tile_path else {'space_id'}
                    if set(request.query_params)!=expected:return deny(422,'scene_cloud_invalid_request')
                    wanted=request.query_params['space_id']
                    if tile_path:
                        raw=await run_in_threadpool(self.scene_pointclouds.tile,wanted,tile_path[1],int(tile_path[2]),request.query_params['index_sha256'])
                        return Response(raw,media_type='application/octet-stream',headers={'Cache-Control':'no-store'})
                    if path=='/api/scene-pointclouds':result=await run_in_threadpool(self.scene_pointclouds.directory,wanted)
                    else:result=await run_in_threadpool(self.scene_pointclouds.status,wanted,path.rsplit('/',1)[-1])
                    return JSONResponse(result,headers={'Cache-Control':'no-store'})
                except ValidationError:return deny(422,'scene_cloud_invalid_request')
                except SceneCloudAuthorizationPending:return deny(503,'accounts_confirmation_required')
                except SceneCloudConflict as exc:return deny(409,str(exc))
                except PermissionError:raise
                except (SceneCloudUnavailable,ValueError,KeyError,OSError,TypeError):return deny(409,'scene_cloud_evidence_unavailable')
            shared=getattr(self.jobs,'ontology_store',None)
            rules=WorkspaceOntologies(shared.root if shared else self.jobs.root.parent/'preview-ontologies',context['principal'])
            request.state.ontology_store=rules
            if path=='/api/ontology-usage':
                try:
                    query=UsageQuery.model_validate(dict(request.query_params))
                    result=await run_in_threadpool(scene_ontology_usage,self.jobs,self.directory,policy,context['principal'],rules,query)
                except ValidationError:return deny(422,'ontology_usage_query_invalid')
                except (ValueError,OSError,KeyError,TypeError):return deny(409,'ontology_usage_unavailable')
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
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
                except (ValueError,TypeError) as exc:
                    return deny(409,public_error(exc,(
                        'ontology_definition_too_large','ontology_draft_already_sealed','ontology_draft_integrity',
                        'ontology_draft_not_found','ontology_draft_revision_changed','ontology_not_found',
                        'ontology_reason_required','ontology_request_conflict','shared_template_read_only',
                        'ontology_definition_invalid','ontology_version_already_sealed',
                    ),'ontology_authoring_failed'))
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
                except ValueError as exc:
                    return deny(409,public_error(exc,(
                        'explicit_space_required','lifecycle_artifact_invalid','lifecycle_changed_refresh_required',
                        'lifecycle_history_mismatch','lifecycle_operation_blocked','lifecycle_reason_required',
                        'lifecycle_records_unavailable','lifecycle_references_changed_refresh_required','lifecycle_transition_invalid',
                        'replacement_cannot_be_self','replacement_publication_required','retired_version_only_accepts_replacement',
                        'retirement_fields_invalid','publication_retired','publication_distribution_paused','publication_not_found',
                        'impact_artifact_invalid','impact_artifact_not_found','impact_kind_not_supported','impact_selection_changed_refresh_required',
                    ),'lifecycle_transition_unavailable'))
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
                        except ValueError as exc:
                            return deny(409,public_error(exc,(
                                'coordinate_edit_unsupported','coordinate_history_invalid','coordinate_request_conflict',
                                'coordinate_revision_binding_invalid','coordinate_revision_changed','coordinate_revision_integrity',
                                'input_not_in_space','pointcloud_axes_invalid','registered_input_changed',
                            ),'input_coordinates_unavailable'))
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
            if path==INPUTS_ROUTE and request.method in ('GET','HEAD'):
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
            history_path=re.fullmatch(r'/api/inputs/([^/]+)/preflight/history',path)
            if history_path:
                try:query=PreflightHistoryQuery.model_validate(dict(request.query_params))
                except ValidationError:return deny(422,'preflight_history_query_invalid')
                if query.sequence is not None and query.before_sequence is not None:
                    return deny(422,'preflight_history_cursor_conflict')
                result=await run_in_threadpool(PreflightRecords(self.jobs.inputs).history,history_path[1],
                    limit=query.limit,before_sequence=query.before_sequence,sequence=query.sequence)
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
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
            if path=='/api/scene-overview':
                if set(request.query_params)!={'space_id'}:return deny(422,'scene_overview_query_invalid')
                identity=request.query_params['space_id']
                if 'build.run' not in policy.capabilities(context['principal'],identity):
                    return JSONResponse({'space_id':identity,'candidate_ref':None,'job':None,'stages':None,'counts':None},headers={'Cache-Control':'no-store'})
                try:result=await run_in_threadpool(scene_overview,self.jobs,identity)
                except (ValueError,OSError,KeyError,TypeError):return deny(409,'scene_overview_unavailable')
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            if path=='/api/workflow':
                from packages.service.preview_workflow import workflow
                from packages.service.preview_publications import PreviewPublications
                identity=request.query_params.get('space_id')
                caps=policy.capabilities(context['principal'],identity)
                try:
                    prep=None
                    if DATA_MANAGE in caps:
                        scoped_sources=await run_in_threadpool(self.workspace_scenes.scoped_sources,context['principal'])
                        prep=await run_in_threadpool(preparation,self.jobs,scoped_sources,identity,request.query_params.get('input_id'),request.query_params.get('batch_id'))
                    result=await run_in_threadpool(workflow,PreviewPublications(self.jobs),identity,
                        request.query_params.get('job_id'),request.query_params.get('publication_id'),prep)
                except PermissionError:raise
                except sqlite3.Error:return deny(503,'workflow_records_unavailable')
                except (ValueError,OSError,KeyError,TypeError):return deny(409,'workflow_unavailable_refresh_required')
                result['business_authorized']=True
                required={'data':DATA_MANAGE,'build':'build.run','ontology':SPACE_PREVIEW,'association':'association.edit','delivery':SPACE_PREVIEW,'space':SPACE_PREVIEW}
                for stage in result['stages']:
                    stage['action']['allowed']=required[stage['action']['module']] in caps
                result['next_action']['allowed']=required[result['next_action']['module']] in caps
                summary=result['summary']
                summary['primary_action']['allowed']=required[summary['primary_action']['module']] in caps
                if summary['work']:summary['work']['action']['allowed']=required[summary['work']['action']['module']] in caps
                for step in summary['journey']['steps']:
                    if step['action']:
                        step['action']['allowed']=required[step['action']['module']] in caps
                if 'build.run' not in caps:
                    summary['journey']=None
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
            if path==INPUTS_ROUTE and request.method=='POST':
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
                record=record|{key:saved[key] for key in ('name','description','address','location') if key in saved}
                caps=sorted(policy.capabilities(context['principal'],identity))
                payload={'space':record,'revision':saved['revision'],'can_manage':'space.manage' in caps,
                         'editable_fields':['name','description','address','location'],
                         'history':saved['history'] if 'space.manage' in caps else []}
                return JSONResponse(payload,headers={'Cache-Control':'no-store'})
            if request.method in ('GET','HEAD') and path in ('/api/projects','/api/spaces'):
                from packages.service.preview_publications import PreviewPublications
                visible=context['visible'];pubs=PreviewPublications(self.jobs)
                if path=='/api/projects':
                    result={'projects':[self.directory.read('project',p) for p in sorted({s['project_id'] for s in visible})]}
                else:
                    values=[]
                    from packages.lifecycle.business_versions import BusinessVersions
                    versions=BusinessVersions(self.jobs.root.parent)
                    await run_in_threadpool(versions.sync)
                    for record in visible:
                        # Only read metadata for this authorized space, before lifecycle
                        # inspection; unassigned/foreign releases never reach the renderer.
                        related=[]
                        for p in sorted(pubs.root.glob('*/publication.json')):
                            saved=json.loads(p.read_bytes())
                            if saved.get('space_id')!=record['id']:continue
                            if saved.get('project_id')!=record['project_id']:raise PermissionError()
                            status=pubs.distribution(saved['id'])
                            related.append(versions.enrich('publication',saved)|status)
                        related.sort(key=lambda v:v['created_at'],reverse=True)
                        latest=related[0] if related else None
                        values.append(record|{'project_name':self.directory.read('project',record['project_id'])['name'],
                            'publications':related,'capabilities':sorted(policy.capabilities(context['principal'],record['id'])),
                            'publication_id':latest['id'] if latest and latest['lifecycle_state']=='active' else None,
                            'state':'no_publication' if not latest else 'preview_published' if latest['lifecycle_state']=='active' else 'distribution_paused'})
                    result={'spaces':values,'legacy_records':'unassigned','access_scope':'authorized_spaces','policy_revision':revision}
                return JSONResponse(result,headers={'Cache-Control':'no-store'})
            return await call_next(request)
        except PreviewUnavailable as exc:
            return deny(409,public_error(exc,(
                'input_preview_evidence_unavailable','input_preview_format_unsupported','preview_geometry_invalid','preview_response_budget',
                'rgbd_preview_evidence_unavailable','rgbd_preview_frame_unavailable',
                'build_preview_evidence_unavailable','build_preview_invalid_request','build_preview_stage_not_ready',
                'build_process_evidence_unavailable','build_process_invalid_request',
            ),'preview_unavailable'))
        except UploadRejected as exc:
            return deny(422,public_error(exc,(
                'invalid_input_label','upload_compression_unsupported','upload_content_validation_failed','upload_duplicate_json_key',
                'upload_existing_evidence_invalid','upload_existing_records_ambiguous','upload_expanded_budget',
                'upload_explicit_scene_required','upload_format_unsupported','upload_manifest_budget','upload_member_budget',
                'upload_member_integrity','upload_members_mismatch','upload_package_invalid','upload_scene_storage_budget',
                'upload_size_budget','upload_unexpected_member','upload_unsafe_member',
            ),'upload_package_invalid'))
        except RecipientConflict as exc:
            return deny(409,public_error(exc,('recipient_request_reused','recipient_revision_changed'),'recipient_conflict'))
        except RecipientsUnavailable:return deny(503,'service_recipients_unavailable')
        except CoordinatesConflict as exc:
            return deny(409,public_error(exc,('coordinate_request_conflict','coordinate_revision_changed'),'input_coordinates_unavailable'))
        except CoordinatesUnavailable:return deny(503,'input_coordinates_unavailable')
        except DescriptionConflict:return deny(409,'input_description_revision_changed')
        except DescriptionUnavailable:return deny(503,'input_descriptions_unavailable')
        except FactsUnavailable as exc:
            return deny(409,public_error(exc,('input_evidence_unreadable','input_evidence_budget','input_evidence_changed',
                'input_facts_format_not_supported','input_evidence_invalid'),'input_evidence_invalid'))
        except WorkspaceScenesConflict as exc:
            return deny(409,public_error(exc,('scene_directory_collision','workspace_scene_context_changed','scene_request_id_reused',
                'created_scene_access_changed_no_repair','scene_binding_collision','scene_project_collision',
                'created_scene_directory_changed_no_repair'),'workspace_scene_creation_unavailable'))
        except WorkspaceScenesUnavailable:return deny(503,'workspace_scene_configuration_unavailable')
        except SettingsConflict:return deny(409,'space_settings_revision_changed')
        except SettingsUnavailable:return deny(503,'space_settings_unavailable')
        except SourcesConflict as exc:
            return deny(409,public_error(exc,('source_catalog_changed','source_settings_revision_changed'),'source_settings_unavailable'))
        except SourcesUnavailable:return deny(503,'source_settings_unavailable')
        except PreflightUnavailable:return deny(503,'preflight_records_unavailable')
        except ApplicationAccessDenied:return deny(403,'application_access_required')
        except SubscriptionDenied:return deny(403,'subscription_required')
        except SubscriptionUnavailable:return deny(503,'subscription_unavailable')
        except IdentityUnavailable:return deny(503,'platform_or_policy_unavailable')
        except IdentityRejected:return deny(401,'access_credential_unavailable')
        except (PermissionError,ValueError,TypeError,KeyError,OSError):return deny(403,'space_access_denied')
