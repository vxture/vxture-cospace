"""Exercise injected persistent adapters from an installed wheel, without a server."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def main():
    wheel = Path(sys.argv[1]).resolve(strict=True)
    script = '''
from pathlib import Path
import json,sys
sys.path.insert(0,sys.argv[1])
from vxture_ontology import builtin_catalog
from vxture_ontology.adapters.authoring_sqlite import SQLiteAuthoringPort
from vxture_ontology.adapters.group_configuration import GroupConfigurationStore
from vxture_ontology.workbench import DefinitionWorkbench

root=Path.cwd()
roles={'editor':{'read','read_private','edit','submit'},
       'reviewer':{'read','read_private','review'},'publisher':{'read','publish'},'reader':{'read'}}
def workspace(actor,scope='park'):
    return DefinitionWorkbench(SQLiteAuthoringPort(root),scope,actor,
        authorize=lambda s,a,action:s==scope and a==actor and action in roles[actor])
editor=workspace('editor')
editor.change(dict(action='save',request_id='a'*32,module_id='core',expected_revision=0,
                   bundle=builtin_catalog().export('core'),base_reference=None))
editor.change(dict(action='submit',request_id='b'*32,module_id='core',expected_revision=1))
groups=GroupConfigurationStore(root)
initial=groups.read('park')
changed=groups.change('park','configuration',dict(request_id='c'*32,expected_revision=initial['revision'],
    group_id=None,name='Synthetic park',description='Adapter acceptance',status='active',sort_order=0,reason='Fixture'))
assert {p.name for p in root.iterdir()}=={'ontology-authoring.sqlite3','ontology-group-configuration.sqlite3'}

# A newly assembled host uses the same stores and resumes the pending approval.
reviewer=workspace('reviewer')
assert reviewer.read('core')['reviews'][0]['can_decide']
assert workspace('reader').read('core')['draft'] is None
assert workspace('reader','other-park').read('core')['releases']==[]
reviewer.change(dict(action='decide',request_id='d'*32,review_id='b'*32,decision='approved',reason='Fixture'))
release=workspace('publisher').change(dict(action='publish',request_id='e'*32,review_id='b'*32,expected_revision=1))
reader=workspace('reader')
assert reader.definition(release['reference'])['modules'][0]['reference']==release['reference']
assert reader.export_release(release['reference'])['reference']==release['reference']
assert GroupConfigurationStore(root).read('park')==changed
assert not any(name=='packages' or name.startswith(('http.server','wsgiref','fastapi','vxture_ontology.local_host'))
               for name in sys.modules)
print(json.dumps({'embedded_adapters':True,'persistent_approval':True,'fixed_release':True,'server':False}))
'''
    with TemporaryDirectory(prefix='ontology-adapters-') as directory:
        result = subprocess.run([sys.executable, '-I', '-S', '-c', script, str(wheel)],
                                cwd=directory, encoding='utf-8', capture_output=True, check=True)
        print(result.stdout.strip())


if __name__ == '__main__':
    main()
