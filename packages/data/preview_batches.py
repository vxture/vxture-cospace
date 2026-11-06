"""Local acquisition organization. Sealed membership is immutable, not quality approval."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid
from pydantic import BaseModel,ConfigDict,Field,StrictInt
from packages.lifecycle.preview_scope import scope,match
from packages.construction.preview_jobs import now
from packages.lifecycle.preview_control_lock import serialized
from packages.lifecycle.preview_control import PreviewControls

PROFILE='cospace.preview-batch/0.1'

class BatchDraft(BaseModel):
    model_config=ConfigDict(extra='forbid')
    space_id:str=Field(min_length=1,max_length=100)
    name:str=Field(min_length=1,max_length=100)
    origin:str=Field(pattern='^(imported_sample|field_collection)$')
    note:str=Field(min_length=1,max_length=500)

class BatchChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    space_id:str=Field(min_length=1,max_length=100)
    expected_revision:StrictInt=Field(ge=0)
    operation:str=Field(pattern='^(replace_members|seal|disable|restore)$')
    reason:str=Field(min_length=1,max_length=500)
    input_ids:list[str]|None=Field(default=None,max_length=100)

def checksum(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def batch_binding(record,registered,revision):
    """Shared admission predicate. Caller owns the read/write snapshot and scope check."""
    if type(revision) is not int or revision!=record['revision']:raise ValueError('batch_changed_refresh_required')
    if record['state']!='sealed':raise ValueError('batch_not_sealed_or_disabled')
    member=next((m for m in record['members'] if registered and m['input_id']==registered['id']),None)
    if member is None:raise ValueError('input_not_in_batch')
    if checksum(record['members'])!=record['sealed_members_sha256'] or checksum(registered)!=member['input_record_sha256']:
        raise ValueError('batch_input_record_changed')
    return {'batch_id':record['id'],'admitted_revision':revision,'sealed_members_sha256':record['sealed_members_sha256'],
            'input_record_sha256':member['input_record_sha256']}

class PreviewBatches:
    def __init__(self,inputs):
        self.inputs=inputs;self.path=inputs.root/'acquisition-batches.sqlite3'

    @contextmanager
    def connection(self,write=False):
        if write:
            db=sqlite3.connect(self.path,timeout=10)
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, space TEXT NOT NULL, record TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT NOT NULL, revision INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(id,revision))')
            db.commit()
        else:db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
        try:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            if write:db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()

    def _read(self,db,identity,ownership):
        if not re.fullmatch(r'batch-[a-f0-9]{16}',identity):raise ValueError('batch_not_found')
        row=db.execute('SELECT record FROM batches WHERE id=?',(identity,)).fetchone()
        if row is None:raise ValueError('batch_not_found')
        record=json.loads(row[0]);match(record,ownership)
        if record['id']!=identity or record['profile']!=PROFILE:raise ValueError('batch_record_invalid')
        latest=db.execute('SELECT revision,record FROM events WHERE id=? ORDER BY revision DESC LIMIT 1',(identity,)).fetchone()
        if not latest or latest[0]!=record['revision'] or json.loads(latest[1])!=record:raise ValueError('batch_history_mismatch')
        if record['state'] not in ('draft','sealed','disabled'):raise ValueError('batch_state_invalid')
        if record.get('sealed_members_sha256') and checksum(record['members'])!=record['sealed_members_sha256']:raise ValueError('batch_members_integrity')
        return record

    def _save(self,db,record):
        raw=json.dumps(record,ensure_ascii=False,sort_keys=True)
        db.execute('INSERT INTO events VALUES (?,?,?)',(record['id'],record['revision'],raw))
        db.execute('INSERT INTO batches VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record',
                   (record['id'],record['space_id'],raw))

    def list(self,space_id):
        ownership=scope(self.inputs.directory,space_id)
        if not space_id:raise ValueError('explicit_space_required')
        if not self.path.exists():return []
        with self.connection() as db:
            return [self._read(db,row[0],ownership) for row in db.execute('SELECT id FROM batches WHERE space=? ORDER BY id',(space_id,))]

    def read(self,identity,space_id):
        ownership=scope(self.inputs.directory,space_id)
        if not space_id or not self.path.exists():raise ValueError('batch_not_found')
        with self.connection() as db:
            record=self._read(db,identity,ownership)
            history=[json.loads(row[0]) for row in db.execute('SELECT record FROM events WHERE id=? ORDER BY revision',(identity,))]
        return record|{'history':history}

    def preparation(self,registered,space_id,identity=None):
        """Read-only batch conditions. No source reads, worker polls, or silent selection."""
        ownership=scope(self.inputs.directory,space_id);match(registered,ownership)
        records=self.list(space_id)
        if identity and not any(r['id']==identity for r in records):raise ValueError('batch_not_in_space')
        members=[r for r in records if any(m['input_id']==registered['id'] for m in r['members'])]
        choices=[]
        for record in members:
            try:batch_binding(record,registered,record['revision']);issue=None
            except ValueError as exc:issue=str(exc)
            choices.append({'id':record['id'],'name':record['name'],'state':record['state'],
                            'revision':record['revision'],'available':issue is None,'issue':issue})
        if identity:
            record=next(r for r in records if r['id']==identity)
            try:batch_binding(record,registered,record['revision']);status='ready';issue=None
            except ValueError as exc:status='blocked';issue=str(exc)
        elif members:status='selection_required' if any(c['available'] for c in choices) else 'blocked';issue='batch_selection_required' if status=='selection_required' else 'batch_not_sealed_or_disabled'
        else:status='not_required';issue=None
        return {'status':status,'selected_batch_id':identity,'choices':choices,'issue':issue,
                'can_submit':status in ('ready','not_required'),'current_files_checked':False}

    @serialized(lambda self:self.inputs.root.parent)
    def create(self,draft):
        ownership=scope(self.inputs.directory,draft.space_id)
        if not draft.name.strip() or not draft.note.strip():raise ValueError('batch_text_required')
        record={'profile':PROFILE,'id':'batch-'+uuid.uuid4().hex[:16],**ownership,'name':draft.name.strip(),
                'origin':draft.origin,'note':draft.note.strip(),'state':'draft','revision':0,'members':[],
                'created_at':now(),'updated_at':now(),'operation':'create','reason':draft.note.strip(),
                'quality':'unverified','robot_ready':False}
        with self.connection(True) as db:self._save(db,record)
        return record

    @serialized(lambda self:self.inputs.root.parent)
    def change(self,identity,request):
        ownership=scope(self.inputs.directory,request.space_id)
        if not request.reason.strip():raise ValueError('batch_reason_required')
        if (request.operation=='replace_members')!=(request.input_ids is not None):raise ValueError('batch_members_only_for_replace')
        if not self.path.exists():raise ValueError('batch_not_found')
        with self.connection(True) as db:
            record=self._read(db,identity,ownership)
            if record['revision']!=request.expected_revision:raise ValueError('batch_changed_refresh_required')
            operation=request.operation
            if operation=='replace_members':
                if record['state']!='draft':raise ValueError('batch_members_frozen')
                if len(set(request.input_ids))!=len(request.input_ids):raise ValueError('batch_duplicate_input')
                members=[]
                for input_id in sorted(request.input_ids):
                    registered=self.inputs.read(input_id);match(registered,ownership)
                    members.append({'input_id':input_id,'label':registered['label'],'input_record_sha256':checksum(registered)})
                record['members']=members
            elif operation=='seal':
                if record['state']!='draft' or not record['members']:raise ValueError('batch_seal_requires_nonempty_draft')
                for member in record['members']:
                    PreviewControls(self.inputs.root.parent,self.inputs.directory).require_active(request.space_id,'input:'+member['input_id'])
                    registered=self.inputs.resolve(member['input_id']);match(registered,ownership)
                    if checksum(registered)!=member['input_record_sha256']:raise ValueError('batch_input_record_changed')
                record.update(state='sealed',sealed_at=now(),sealed_members_sha256=checksum(record['members']))
            elif operation=='disable':
                if record['state']=='disabled':raise ValueError('batch_already_disabled')
                record.update(resume_state=record['state'],state='disabled')
            else:
                if record['state']!='disabled':raise ValueError('batch_not_disabled')
                record['state']=record.pop('resume_state')
            record.update(revision=record['revision']+1,updated_at=now(),operation=operation,reason=request.reason.strip())
            self._save(db,record)
        return record

    @contextmanager
    def admit(self,registered,ownership,identity=None,revision=None):
        # Keep the write lock through publishing the job record and starting its process.
        # An overlapping disable is ordered after this admission, not retroactive cancellation.
        if not self.path.exists():
            if identity is not None or revision is not None:raise ValueError('batch_not_found')
            yield None;return
        with self.connection(True) as db:
            batches=[self._read(db,row[0],ownership) for row in db.execute('SELECT id FROM batches WHERE space=?',(ownership.get('space_id'),))]
            member_batches=[r for r in batches if any(m['input_id']==registered['id'] for m in r['members'])] if registered else []
            if identity is None:
                if revision is not None:raise ValueError('batch_id_required')
                if member_batches:raise ValueError('batch_selection_required')
                yield None;return
            record=self._read(db,identity,ownership)
            yield {**batch_binding(record,registered,revision),**ownership}

def batch_results(batches,jobs,publications,identity,space_id):
    """Read job attempts and fixed model provenance; never infer from shared input IDs."""
    record=batches.read(identity,space_id);ownership=scope(jobs.directory,space_id)
    attempts=[];releases=[]
    for path in sorted(jobs.root.glob('*/job.json')):
        if path.parent.name.startswith('.'):continue
        job=json.loads(path.read_bytes())
        if job.get('batch_ref',{}).get('batch_id')!=identity:continue
        match(job,ownership);match(job['batch_ref'],ownership)
        attempts.append({k:job.get(k) for k in ('id','state','created_at','method','input_id','base_candidate_id','batch_ref')})
    for path in sorted(publications.root.glob('preview-*/publication.json')):
        saved=json.loads(path.read_bytes())
        if saved.get('space_id')!=space_id:continue
        model=json.loads((path.parent/'model.json').read_bytes())
        ref=model.get('source',{}).get('batch_ref')
        if not ref or ref.get('batch_id')!=identity:continue
        match(ref,ownership)
        releases.append({'id':saved['id'],'candidate_id':saved['candidate_id'],'created_at':saved['created_at'],
                         'batch_ref':ref,'state':'fixed_preview','integrity':'not_checked'})
    return {'profile':'cospace.preview-batch-results/0.1','batch':record,'attempts':attempts,'publications':releases,
            'jobs_polled':False,'source_files_rechecked':False,'quality':'unverified','robot_ready':False}
