"""External lifecycle controls; immutable model/source/publication bytes are untouched."""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
from pydantic import BaseModel,ConfigDict,Field,StrictInt
from packages.lifecycle.preview_control_lock import mutation_guard
from packages.lifecycle.preview_scope import scope,match

PROFILE='cospace.preview-artifact-control/0.1'
REPORT='cospace.preview-artifact-control-report/0.1'
TITLES={'disable_input':'停用资料','archive_input':'归档资料','archive_candidate':'归档候选','pause_distribution':'暂停分发','restore':'恢复','retire_publication':'退役版本'}

class ControlChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    space_id:str=Field(min_length=1,max_length=100)
    artifact:str=Field(min_length=1,max_length=150)
    expected_revision:StrictInt=Field(ge=0)
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    operation:str=Field(pattern=r'^(disable_input|archive_input|archive_candidate|pause_distribution|restore|retire_publication)$')
    reason:str=Field(min_length=1,max_length=500)
    replacement_publication_id:str|None=Field(default=None,pattern=r'^preview-[a-f0-9]{16}$')
    retirement_kind:str|None=Field(default=None,pattern=r'^(superseded|erroneous)$')

class PreviewControls:
    def __init__(self,runtime,directory=None):
        self.runtime=Path(runtime);self.directory=directory;self.path=self.runtime/'preview-lifecycle.sqlite3'

    @contextmanager
    def connection(self,write=False):
        if write:
            db=sqlite3.connect(self.path,timeout=10)
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE IF NOT EXISTS controls (space TEXT NOT NULL, artifact TEXT NOT NULL, record TEXT NOT NULL, PRIMARY KEY(space,artifact))')
            db.execute('CREATE TABLE IF NOT EXISTS events (space TEXT NOT NULL, artifact TEXT NOT NULL, revision INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(space,artifact,revision))')
            db.commit()
        else:db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
        try:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN');yield db
            if write:db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    def key(self,artifact):
        if not re.fullmatch(r'(input:input-[a-f0-9]{16}|candidate:build-[A-Za-z0-9-]+|publication:preview-[a-f0-9]{16})',artifact):raise ValueError('lifecycle_artifact_invalid')

    def _read(self,db,ownership,artifact):
        row=db.execute('SELECT record FROM controls WHERE space=? AND artifact=?',(ownership['space_id'],artifact)).fetchone()
        history=[json.loads(row[0]) for row in db.execute('SELECT record FROM events WHERE space=? AND artifact=? ORDER BY revision',(ownership['space_id'],artifact))]
        if row is None:
            if history:raise ValueError('lifecycle_history_mismatch')
            return {'profile':PROFILE,**ownership,'artifact':artifact,'lifecycle_state':'active','revision':0,'resume_state':None,'history':[]}
        record=json.loads(row[0]);match(record,ownership)
        if (record.get('profile')!=PROFILE or record.get('artifact')!=artifact or not history or history[-1]!=record
                or [h.get('revision') for h in history]!=list(range(1,record.get('revision',0)+1))):raise ValueError('lifecycle_history_mismatch')
        prior='active';resume=None
        for h in history:
            match(h,ownership)
            if h.get('artifact')!=artifact or h.get('profile')!=PROFILE or not isinstance(h.get('reason'),str) or not h['reason'].strip():raise ValueError('lifecycle_history_mismatch')
            operation=h.get('operation')
            if operation not in self.operations(artifact,prior):raise ValueError('lifecycle_history_mismatch')
            state,next_resume=self.destination(prior,resume,operation)
            if h.get('previous_state')!=prior or h.get('lifecycle_state')!=state or h.get('resume_state')!=next_resume:raise ValueError('lifecycle_history_mismatch')
            prior,resume=state,next_resume
        return {**record,'history':history}

    def read(self,space_id,artifact):
        self.key(artifact);ownership=scope(self.directory,space_id)
        if not space_id:raise ValueError('explicit_space_required')
        if not self.path.exists():return {'profile':PROFILE,**ownership,'artifact':artifact,'lifecycle_state':'active','revision':0,'resume_state':None,'history':[]}
        with self.connection() as db:return self._read(db,ownership,artifact)

    def saved(self,space_id):
        ownership=scope(self.directory,space_id)
        if not self.path.exists():return []
        with self.connection() as db:
            keys={row[0] for row in db.execute('SELECT artifact FROM controls WHERE space=?',(space_id,))}|{row[0] for row in db.execute('SELECT DISTINCT artifact FROM events WHERE space=?',(space_id,))}
            for key in keys:self.key(key)
            return [self._read(db,ownership,key) for key in sorted(keys)]

    def require_active(self,space_id,artifact):
        # Legacy unscoped reads stay compatible; no lifecycle write accepts this scope.
        if space_id is None:return
        try:record=self.read(space_id,artifact)
        except (sqlite3.Error,OSError,KeyError,TypeError) as exc:raise ValueError('lifecycle_records_unavailable') from exc
        if record['lifecycle_state']!='active':raise ValueError('lifecycle_'+record['lifecycle_state']+'_new_use_blocked')

    @staticmethod
    def operations(artifact,state):
        if artifact.startswith('publication:'):return ['pause_distribution','retire_publication'] if state=='active' else ['restore','retire_publication'] if state=='paused' else ['retire_publication'] if state=='retired' else []
        if state=='archived':return ['restore']
        if artifact.startswith('candidate:'):return ['archive_candidate'] if state=='active' else []
        return ['disable_input','archive_input'] if state=='active' else ['restore','archive_input'] if state=='disabled' else []

    @staticmethod
    def destination(state,resume,operation):
        if operation=='restore':return (resume if state=='archived' else 'active'),None
        if operation=='disable_input':return 'disabled',None
        if operation=='pause_distribution':return 'paused',None
        if operation=='retire_publication':return 'retired',None
        return 'archived',state

    def report(self,publications,space_id,artifact):
        from packages.lifecycle.preview_impact import impact
        from packages.data.preview_batches import checksum
        self.key(artifact)
        evidence=impact(publications,space_id,artifact)
        saved=self.saved(space_id);current=next((r for r in saved if r['artifact']==artifact),self.read(space_id,artifact))
        actions=[]
        for op in self.operations(artifact,current['lifecycle_state']):
            if current['lifecycle_state']=='retired' and current.get('replacement_publication_id'):continue
            blocks=['dependency_records_incomplete'] if evidence['issues'] else []
            if op not in ('restore','retire_publication'):blocks=next(p['blockers'] for p in evidence['plans'] if p['operation']==op)
            state,_=self.destination(current['lifecycle_state'],current['resume_state'],op)
            actions.append({'operation':op,'title':'补充替代版本' if current['lifecycle_state']=='retired' else TITLES[op],'target_state':state,'blockers':blocks,'allowed':not blocks})
        return {'profile':REPORT,'space_id':space_id,'artifact':artifact,'record':current,'impact':evidence,'actions':actions,
                'snapshot_sha256':checksum({'impact':evidence['snapshot_sha256'],'controls':saved}),
                'identity':'local_engineer_unverified_identity','publication_control_supported':True,'quality':'unverified','robot_ready':False}

    def change(self,publications,request,actor='local_engineer_unverified_identity'):
        from packages.construction.preview_jobs import now
        jobs=publications.jobs
        if not request.reason.strip():raise ValueError('lifecycle_reason_required')
        self.key(request.artifact)
        # Global mutation -> job completion/selection -> SQLite; every admission uses the same order.
        with mutation_guard(self.runtime),jobs.lock:
            is_retire=request.operation=='retire_publication'
            if not is_retire and (request.retirement_kind or request.replacement_publication_id):raise ValueError('retirement_fields_invalid')
            if is_retire:
                if not request.artifact.startswith('publication:') or not request.retirement_kind:raise ValueError('retirement_fields_invalid')
                if request.retirement_kind=='superseded' and not request.replacement_publication_id:raise ValueError('replacement_publication_required')
                if request.replacement_publication_id:
                    if request.artifact=='publication:'+request.replacement_publication_id:raise ValueError('replacement_cannot_be_self')
                    replacement,_=publications.read(request.replacement_publication_id)
                    match(replacement,scope(self.directory,request.space_id))
                    publications.require_distributing(request.replacement_publication_id)
                existing=self.read(request.space_id,request.artifact)
                # A lost response may replay the exact committed retirement, never another reason or target.
                if existing['lifecycle_state']=='retired' and existing['revision']==request.expected_revision+1:
                    if (existing.get('reason')==request.reason.strip() and existing.get('retirement_kind')==request.retirement_kind
                            and existing.get('replacement_publication_id')==request.replacement_publication_id
                            and existing.get('actor')==actor and existing.get('checked_snapshot_sha256')==request.expected_snapshot_sha256):return existing
                if existing['lifecycle_state']=='retired':
                    if (existing.get('replacement_publication_id') or not request.replacement_publication_id
                            or request.retirement_kind!=existing.get('retirement_kind')):raise ValueError('retired_version_only_accepts_replacement')
            report=self.report(publications,request.space_id,request.artifact);record=report['record']
            if record['revision']!=request.expected_revision:raise ValueError('lifecycle_changed_refresh_required')
            if report['snapshot_sha256']!=request.expected_snapshot_sha256:raise ValueError('lifecycle_references_changed_refresh_required')
            action=next((a for a in report['actions'] if a['operation']==request.operation),None)
            if action is None:raise ValueError('lifecycle_transition_invalid')
            if not action['allowed']:raise ValueError('lifecycle_operation_blocked')
            if request.operation=='restore' and request.artifact.startswith('input:') and action['target_state']=='active':
                jobs.inputs.resolve(request.artifact.split(':',1)[1])
            state,resume=self.destination(record['lifecycle_state'],record['resume_state'],request.operation)
            updated={k:v for k,v in record.items() if k!='history'}
            updated.update(lifecycle_state=state,resume_state=resume,previous_state=record['lifecycle_state'],revision=record['revision']+1,
                           operation=request.operation,reason=request.reason.strip(),updated_at=now(),actor=actor,
                           checked_snapshot_sha256=report['snapshot_sha256'])
            if is_retire:updated.update(retirement_kind=request.retirement_kind,replacement_publication_id=request.replacement_publication_id)
            with self.connection(True) as db:
                latest=self._read(db,scope(self.directory,request.space_id),request.artifact)
                if latest['revision']!=record['revision']:raise ValueError('lifecycle_changed_refresh_required')
                raw=json.dumps(updated,ensure_ascii=False,sort_keys=True)
                db.execute('INSERT INTO events VALUES (?,?,?,?)',(request.space_id,request.artifact,updated['revision'],raw))
                db.execute('INSERT INTO controls VALUES (?,?,?) ON CONFLICT(space,artifact) DO UPDATE SET record=excluded.record',(request.space_id,request.artifact,raw))
            return {**updated,'history':record['history']+[updated]}
