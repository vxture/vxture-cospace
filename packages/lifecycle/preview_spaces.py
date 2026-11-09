"""Local project/space directory. No publication ownership is inferred."""
import json
from pathlib import Path
import re
import uuid
from packages.construction.preview_jobs import now
from packages.lifecycle.space_settings import SpaceSettings


class PreviewSpaces:
    def __init__(self, root):
        self.root=Path(root)
        for kind in ('project','space'): (self.root/kind).mkdir(parents=True,exist_ok=True)
        self.settings=SpaceSettings(self.root)

    def read(self,kind,identity):
        if kind not in ('project','space') or not re.fullmatch(kind+r'-[a-f0-9]{16}',identity):
            raise ValueError('directory_record_not_found')
        path=self.root/kind/(identity+'.json')
        if not path.is_file(): raise ValueError('directory_record_not_found')
        record=json.loads(path.read_bytes())
        if record['id']!=identity: raise ValueError('directory_record_invalid')
        if kind=='space':
            saved=self.settings.read(identity)
            record.update({k:saved[k] for k in ('name','description','address','location') if k in saved})
        return record

    def list(self,kind):
        return [self.read(kind,p.stem) for p in sorted((self.root/kind).glob('*.json'))]

    def create(self,kind,name,project_id=None,description=''):
        if kind not in ('project','space'): raise ValueError('invalid_directory_kind')
        if not 1<=len(name.strip())<=100 or len(description)>500: raise ValueError('invalid_directory_name')
        if kind=='space': self.read('project',project_id or '')
        identity=kind+'-'+uuid.uuid4().hex[:16]
        record={'profile':'cospace.preview-'+kind+'/0.1','id':identity,
                'name':name.strip(),'created_at':now()}
        if kind=='space':
            record.update(project_id=project_id,description=description.strip(),
                          publication_id=None,state='no_publication')
        pending=self.root/kind/(identity+'.pending')
        with pending.open('x',encoding='utf-8') as stream: json.dump(record,stream,ensure_ascii=False,indent=2)
        pending.rename(self.root/kind/(identity+'.json'))
        return record
