"""Local immutable preview snapshots, separate from production release profiles."""
from packages.views.viewer_entry import write_viewer_entry
import json
from pathlib import Path
import re
import shutil
import uuid
from packages.construction.preview_jobs import now
from packages.lifecycle.preview_scope import scope,match,owned
from packages.construction.preview_model import PreviewModel,digest
from packages.lifecycle.preview_control_lock import serialized


class PreviewPublications:
    def __init__(self,jobs):
        self.jobs=jobs; self.root=jobs.root/'publications'; self.root.mkdir(exist_ok=True)

    def list(self):
        return sorted([json.loads(p.read_bytes()) for p in self.root.glob('preview-*/publication.json')],
                      key=lambda r:r['created_at'],reverse=True)

    def distribution(self,identity):
        """Admission metadata only. Internal snapshot reads remain separate for recovery."""
        if not re.fullmatch(r'preview-[a-f0-9]{16}',identity):raise ValueError('publication_not_found')
        path=self.root/identity/'publication.json'
        if not path.is_file():raise ValueError('publication_not_found')
        record=json.loads(path.read_bytes())
        if record.get('id')!=identity:raise ValueError('publication_record_invalid')
        ownership=scope(self.jobs.directory,record.get('space_id'));match(record,ownership)
        manifest=json.loads((path.parent/'model.json').read_bytes());match(manifest,ownership)
        if record.get('candidate_id')!=manifest.get('id') or record.get('model_manifest_sha256')!=digest(path.parent/'model.json'):
            raise ValueError('publication_record_invalid')
        if ownership:
            control=self.jobs.controls.read(ownership['space_id'],'publication:'+identity)
            result={'lifecycle_state':control['lifecycle_state'],'lifecycle_revision':control['revision']}
            if control['lifecycle_state']=='retired':result.update(retirement_kind=control.get('retirement_kind'),replacement_publication_id=control.get('replacement_publication_id'),retirement_reason=control['reason'])
            return result
        # Unassigned legacy publications cannot be changed by the scoped lifecycle API.
        return {'lifecycle_state':'active','lifecycle_revision':0}

    def require_distributing(self,identity):
        status=self.distribution(identity)
        if status['lifecycle_state']=='retired':raise ValueError('publication_retired')
        if status['lifecycle_state']!='active':raise ValueError('publication_distribution_paused')
        return status

    def directory_entries(self):
        result=[]
        for record in self.list():
            status=self.distribution(record['id'])
            # Paused metadata supports management/recovery, never embeds comparison contents or files.
            if status['lifecycle_state']!='active':
                record={k:record[k] for k in ('id','candidate_id','created_at','space_id','project_id','state','quality','production_ready') if k in record}
            result.append({**record,**status})
        return result

    @serialized(lambda self:self.jobs.root.parent)
    def publish(self,candidate_id,expected_revision,space_id=None,*,request_id=None):
        ownership=scope(self.jobs.directory,space_id)
        if request_id is not None:
            if not re.fullmatch(r'[a-f0-9]{32}',request_id):raise ValueError('publication_request_invalid')
            existing=next((r for r in self.list() if r.get('space_id')==space_id and r.get('request_id')==request_id),None)
            if existing:
                if existing['candidate_id']!=candidate_id or existing['selection_revision']!=expected_revision:
                    raise ValueError('publication_request_conflict')
                return existing
        source=self.jobs.model(candidate_id)
        match(source.manifest,ownership)
        self.jobs.controls.require_active(space_id,'candidate:'+candidate_id)
        # Single server: selection checks and snapshot copy share the selection lock.
        with self.jobs.lock:
            path=self.jobs.selection_path(space_id)
            selection=json.loads(path.read_bytes()) if path.exists() else {}
            if path.exists(): match(selection,ownership)
            if (selection.get('candidate_id')!=candidate_id or selection.get('revision')!=expected_revision):
                raise ValueError('selection_changed_refresh_required')
            if digest(source.root/'model.json')!=selection['model_manifest_sha256']:
                raise ValueError('selected_model_integrity_changed')
            identity='preview-'+uuid.uuid4().hex[:16]
            staging=self.root/('.pending-'+identity); staging.mkdir()
            for name in [*source.manifest['members'],'model.json']:
                if Path(name).name!=name: raise ValueError('invalid_member_name')
                shutil.copyfile(source.root/name,staging/name)
            if (source.root/'offline-checks.json').exists():
                shutil.copyfile(source.root/'offline-checks.json',staging/'offline-checks.json')
            write_viewer_entry(staging,source.manifest,publication_id=identity)
            PreviewModel(staging)
            if digest(staging/'model.json')!=selection['model_manifest_sha256']:
                raise ValueError('copy_integrity_changed')
            record={'profile':'cospace.local-preview-publication/0.1','id':identity,
                'created_at':now(),'candidate_id':candidate_id,'selection_revision':expected_revision,
                'model_manifest_sha256':digest(staging/'model.json'),
                'source_model_sha256':source.manifest['members']['spatial.npz']['sha256'],
                'preview_url':f'/publications/{identity}/','query_url':f'/publications/{identity}/api/query',
                'state':'preview_published','quality':'unverified','production_ready':False,**ownership,
                'files':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in staging.iterdir() if p.is_file()}}
            if selection.get('selection_review'):
                record['selection_review']=selection['selection_review']
            if request_id is not None:record['request_id']=request_id
            if source.manifest.get('derivation'):
                record['derivation']=source.manifest['derivation']
            (staging/'publication.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
            staging.rename(self.root/identity)
            return record

    def read(self,identity):
        if not re.fullmatch(r'preview-[a-f0-9]{16}',identity): raise ValueError('publication_not_found')
        root=self.root/identity
        if not (root/'publication.json').is_file(): raise ValueError('publication_not_found')
        record=json.loads((root/'publication.json').read_bytes())
        for name,member in record['files'].items():
            if Path(name).name!=name or digest(root/name)!=member['sha256'] or (root/name).stat().st_size!=member['bytes']:
                raise ValueError('publication_integrity_changed')
        model=PreviewModel(root)
        match(model.manifest,owned(record))
        if record.get('derivation')!=model.manifest.get('derivation'):raise ValueError('publication_view_composition_mismatch')
        return record,model
