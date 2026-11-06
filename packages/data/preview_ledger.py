"""Immutable local asset ledger versions. No external business system calls."""
import json
import threading
import uuid
from pathlib import Path
import re
from packages.construction.preview_jobs import now
from packages.lifecycle.preview_scope import scope,match
from packages.spatial.preview_business import LedgerRecord,record_bytes,record_sha


class PreviewLedger:
    def __init__(self,root,directory):
        self.root=Path(root);self.directory=directory;self.lock=threading.Lock()

    def read(self,identity,sha256=None):
        if not re.fullmatch(r'ledger-[a-f0-9]{16}',identity):raise ValueError('ledger_not_found')
        raw=(self.root/(identity+'.json')).read_bytes()
        record=LedgerRecord.model_validate(json.loads(raw)).model_dump()
        if record['record_id']!=identity or (sha256 is not None and record_sha(record)!=sha256):
            raise ValueError('ledger_integrity_changed')
        return {'ref':{'record_id':identity,'sha256':record_sha(record)},'record':record}

    def list(self,space_id):
        ownership=scope(self.directory,space_id)
        return [value for p in sorted(self.root.glob('ledger-*.json'))
                if (value:=self.read(p.stem))['record'].get('space_id')==ownership['space_id']
                and value['record']['project_id']==ownership['project_id']]

    def register(self,request):
        ownership=scope(self.directory,request.space_id)
        payload=request.model_dump()
        with self.lock:
            for item in self.list(request.space_id):
                old=item['record']
                if all(old[k]==payload[k] for k in ('source_system','external_id','version')):
                    if any(old[k]!=payload[k] for k in payload):raise ValueError('ledger_version_conflict')
                    return {'created':False,**item}
            record={'profile':'cospace.preview-ledger/0.1','record_id':'ledger-'+uuid.uuid4().hex[:16],
                    **payload,**ownership,'created_at':now(),'confirmation':'unverified'}
            LedgerRecord.model_validate(record)
            self.root.mkdir(parents=True,exist_ok=True)
            pending=self.root/(record['record_id']+'.pending')
            with pending.open('xb') as stream:stream.write(record_bytes(record))
            pending.rename(self.root/(record['record_id']+'.json'))
            return {'created':True,**self.read(record['record_id'])}

    def resolve(self,ref,space_id):
        value=self.read(ref.record_id,ref.sha256);match(value['record'],scope(self.directory,space_id));return value
