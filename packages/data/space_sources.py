"""Per-space registration choices from a trusted startup catalog; never browser paths."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourcesUnavailable(RuntimeError):
    pass


class SourcesConflict(ValueError):
    pass


class SourceChange(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    space_id:str=Field(pattern=r'^space-[a-f0-9]{16}$')
    expected_revision:int=Field(ge=0)
    catalog_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    enabled_source_ids:list[str]=Field(max_length=100)
    reason:str=Field(min_length=1,max_length=500)

    @field_validator('enabled_source_ids')
    @classmethod
    def unique(cls,value):
        if len(value)!=len(set(value)):raise ValueError('duplicate_source_id')
        return sorted(value)

    @field_validator('reason')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('reason_required')
        return value.strip()


class SavedSources(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    revision:int=Field(ge=0)
    bindings:dict[str,str]
    history:list[dict]


class SpaceSources:
    def __init__(self,root,sources):
        self.path=Path(root)/'registration-sources.sqlite3'
        self.sources={key:dict(value) for key,value in sources.items()}
        def digest(value):
            return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.fingerprints={key:digest({'format':value.get('format','nyu_rgbd_with_existing_poses'),
            'snapshot':str(Path(value['snapshot']).resolve()),
            'tracking':str(Path(value['tracking']).resolve()) if value.get('tracking') else None}) for key,value in self.sources.items()}
        self.catalog_sha256=digest(self.fingerprints)

    @staticmethod
    def decode(raw):
        try:return SavedSources.model_validate(json.loads(raw)).model_dump()
        except (ValueError,TypeError) as exc:raise SourcesUnavailable('source_settings_unavailable') from exc

    def read(self,space_id):
        if not self.path.exists():return {'revision':0,'bindings':{},'history':[]}
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                row=db.execute('SELECT record FROM settings WHERE space_id=?',(space_id,)).fetchone()
                return self.decode(row[0]) if row else {'revision':0,'bindings':{},'history':[]}
        except (OSError,sqlite3.Error) as exc:raise SourcesUnavailable('source_settings_unavailable') from exc

    def effective(self,saved):
        return {key:self.sources[key] for key,value in saved['bindings'].items()
                if key in self.sources and self.fingerprints[key]==value}

    def view(self,space_id,can_manage,saved=None):
        saved=self.read(space_id) if saved is None else saved
        enabled=self.effective(saved)
        def public(key):
            value=self.sources[key]
            return {'id':key,'label':value['label'],'format':value.get('format','nyu_rgbd_with_existing_poses')}
        return {'space_id':space_id,'revision':saved['revision'],'can_manage':can_manage,
            'catalog_sha256':self.catalog_sha256,'sources':[public(key) for key in sorted(enabled)],
            'catalog':[public(key)|{'enabled':key in enabled,'needs_confirmation':key in saved['bindings'] and key not in enabled}
                       for key in sorted(self.sources)] if can_manage else [],
            'unavailable_source_ids':sorted(set(saved['bindings'])-set(enabled)) if can_manage else [],
            'history':saved['history'] if can_manage else []}

    def change(self,change,actor):
        if change.catalog_sha256!=self.catalog_sha256:raise SourcesConflict('source_catalog_changed')
        if any(key not in self.sources for key in change.enabled_source_ids):raise ValueError('registration_source_not_allowed')
        after={key:self.fingerprints[key] for key in change.enabled_source_ids}
        try:
            with closing(sqlite3.connect(self.path,timeout=10)) as db:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS settings(space_id TEXT PRIMARY KEY,record TEXT NOT NULL)')
                    db.execute('BEGIN IMMEDIATE')
                    row=db.execute('SELECT record FROM settings WHERE space_id=?',(change.space_id,)).fetchone()
                    before=self.decode(row[0]) if row else {'revision':0,'bindings':{},'history':[]}
                    if before['revision']!=change.expected_revision:raise SourcesConflict('source_settings_revision_changed')
                    if before['bindings']==after:return before
                    event={'revision':before['revision']+1,'actor':actor,'changed_at':datetime.now(timezone.utc).isoformat(),
                           'reason':change.reason,'before':sorted(before['bindings']),'after':sorted(after),
                           'catalog_sha256':self.catalog_sha256}
                    saved={'revision':event['revision'],'bindings':after,'history':before['history']+[event]}
                    db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(change.space_id,json.dumps(saved,ensure_ascii=False)))
                    return saved
        except (OSError,sqlite3.Error) as exc:raise SourcesUnavailable('source_settings_unavailable') from exc
