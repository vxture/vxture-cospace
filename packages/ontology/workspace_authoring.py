"""Workspace-owned drafts and immutable rule versions; shared seeds stay read-only."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from packages.lifecycle.preview_control_lock import serialized
from packages.ontology.preview_versions import PreviewOntologies, definition, digest, MAX_BYTES


def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


class DraftChange(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    draft_id:str=Field(pattern=r'^draft-[a-f0-9]{32}$')
    expected_revision:StrictInt=Field(ge=0)
    request_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    definition:dict
    reason:str=Field(min_length=1,max_length=500)


class SealDraft(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    draft_id:str=Field(pattern=r'^draft-[a-f0-9]{32}$')
    expected_revision:StrictInt=Field(ge=1)
    expected_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


class WorkspaceOntologies(PreviewOntologies):
    def __init__(self,root,principal):
        self.root=Path(root).resolve()
        self.owner={'issuer':principal.issuer,'org_id':principal.org_id,'workspace_id':principal.workspace_id}
        self.workspace_key=hashlib.sha256(encode(self.owner)).hexdigest()
        self.private_root=self.root/'.workspaces'/self.workspace_key
        self.db=self.private_root/'drafts.sqlite3'

    def path(self,identity,version):
        shared=super().path(identity,version)
        if shared.exists():return shared
        return self.private_root/identity/version

    def read(self,identity,version,expected_sha256=None):
        # Shared template identities cannot be shadowed by private rules.
        target=self.path(identity,version)
        if target.exists() and not target.is_relative_to(self.private_root):return PreviewOntologies(self.root).read(identity,version,expected_sha256)
        if self.private_root.exists():return PreviewOntologies(self.private_root).read(identity,version,expected_sha256)
        raise ValueError('ontology_not_found')

    def list(self):
        shared=PreviewOntologies(self.root).list()
        private=PreviewOntologies(self.private_root).list() if self.private_root.exists() else []
        return [r|{'scope':'shared_template'} for r in shared]+[r|{'scope':'workspace_rules'} for r in private]

    def drafts(self):
        if not self.db.exists():return []
        with closing(sqlite3.connect(self.db.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            rows=db.execute('SELECT record FROM events ORDER BY draft_id,revision').fetchall()
        groups={}
        for row in rows:
            event=json.loads(row[0]);identity=event['draft_id'];history=groups.setdefault(identity,[])
            unsigned={k:v for k,v in event.items() if k!='event_sha256'}
            if (event['revision']!=len(history)+1 or event['workspace']!=self.owner
                    or digest(encode(event['definition']))!=event['sha256'] or digest(encode(unsigned))!=event['event_sha256']
                    or event['previous_sha256']!=(history[-1]['event_sha256'] if history else None)):
                raise ValueError('ontology_draft_integrity')
            history.append(event)
        result=[]
        for history in groups.values():
            row=history[-1];doc=row['definition'];sealed=False
            try:sealed=self.read(doc.get('ontology_id',''),doc.get('version',''))[0]['sha256']==row['sha256']
            except TypeError:pass
            except ValueError as exc:
                if str(exc)!='ontology_not_found':raise
            result.append(row|{'history':history,'sealed':sealed})
        return result

    def draft(self,identity):
        row=next((v for v in self.drafts() if v['draft_id']==identity),None)
        if row is None:raise ValueError('ontology_draft_not_found')
        return row

    @serialized(lambda self:self.root.parent)
    def save(self,change,actor):
        raw=encode(change.definition)
        if len(raw)>MAX_BYTES:raise ValueError('ontology_definition_too_large')
        if not change.reason.strip():raise ValueError('ontology_reason_required')
        state=next((d for d in self.drafts() if d['draft_id']==change.draft_id),None)
        history=state['history'] if state else []
        request_sha=digest(encode(change.model_dump()))
        previous=next((e for e in history if e['request_id']==change.request_id),None)
        if previous:
            if previous['request_sha256']!=request_sha or previous['actor']!=actor:raise ValueError('ontology_request_conflict')
            return state
        if change.expected_revision!=len(history):raise ValueError('ontology_draft_revision_changed')
        if state and state['sealed']:raise ValueError('ontology_draft_already_sealed')
        now=datetime.now(timezone.utc).isoformat()
        event={'draft_id':change.draft_id,'revision':len(history)+1,'definition':change.definition,
               'sha256':digest(raw),'workspace':self.owner,'actor':actor,'changed_at':now,'reason':change.reason.strip(),
               'request_id':change.request_id,'request_sha256':request_sha,
               'previous_sha256':history[-1]['event_sha256'] if history else None}
        event['event_sha256']=digest(encode(event))
        self.private_root.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.db,timeout=10)) as db:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS events(draft_id TEXT,revision INTEGER,record TEXT NOT NULL,PRIMARY KEY(draft_id,revision))')
                db.execute('INSERT INTO events VALUES(?,?,?)',(change.draft_id,event['revision'],encode(event).decode()))
        return self.draft(change.draft_id)

    @serialized(lambda self:self.root.parent)
    def seal(self,change,actor):
        draft=self.draft(change.draft_id)
        if draft['revision']!=change.expected_revision or draft['sha256']!=change.expected_sha256:
            raise ValueError('ontology_draft_revision_changed')
        raw=encode(draft['definition']);doc=definition(raw)
        if PreviewOntologies(self.root).path(doc['ontology_id'],doc['version']).exists():raise ValueError('shared_template_read_only')
        return PreviewOntologies(self.private_root).register_bytes(raw,{
            'workspace':self.owner,'actor':actor,'sealed_at':datetime.now(timezone.utc).isoformat(),
            'draft_id':draft['draft_id'],'revision':draft['revision'],'reason':draft['reason'],
            'draft_event_sha256':draft['event_sha256']})

    @staticmethod
    def validate(value):
        try:definition(encode(value));return {'status':'passed','issues':[],'sha256':digest(encode(value))}
        except (ValueError,TypeError):return {'status':'failed','issues':['类型、属性或关系规则不符合当前规范，请检查ID、长度及关系端点。']}
