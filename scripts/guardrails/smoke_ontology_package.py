"""Exercise a built wheel outside the checkout, without site packages."""
from email.parser import BytesParser
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


def main():
    wheel = Path(sys.argv[1]).resolve()
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert all(name.startswith(('vxture_ontology/', 'vxture_ontology-')) for name in names)
        metadata = next(name for name in names if name.endswith('.dist-info/METADATA'))
        assert not BytesParser().parsebytes(archive.read(metadata)).get_all('Requires-Dist')
    script = '''
import json,sys
from contextlib import contextmanager
from copy import deepcopy
sys.path.insert(0,sys.argv[1])
import vxture_ontology
from vxture_ontology import Catalog,builtin_catalog,canonical_bytes,instance_schema,park_baseline_rules,validate_instances
from vxture_ontology.workbench import DefinitionWorkbench
assert instance_schema()['$id']=='urn:vxture:schema:ontology-instances:0.1'
assert len(park_baseline_rules()['cardinalities'])==9
assert validate_instances(b'{}',builtin_catalog())['valid'] is False
assert validate_instances(b'{"a":1,"a":2}',builtin_catalog())['diagnostics'][0]['code']=='duplicate_key'
instance=json.loads(sys.stdin.buffer.read())
assert validate_instances(canonical_bytes(instance),builtin_catalog(),rule_set='park-baseline')['valid']
from vxture_ontology.exchange import catalog_from_exchanges,export_closure,parse_closure,project_owl_classes
catalog=builtin_catalog()
references={m['reference']['module_id']:m['reference'] for m in catalog.describe()['modules']}
closures=[canonical_bytes(export_closure(catalog.export(key),references[key]))
          for key in ('built_environment','electrical','monitoring','operations')]
assert canonical_bytes(parse_closure(closures[1]))==closures[1]
assert project_owl_classes(closures[1])['omissions']
assert validate_instances(canonical_bytes(instance),catalog_from_exchanges(closures),rule_set='park-baseline')['valid']
instance['assertions'][5]['object_id']='cabinet'
report=validate_instances(canonical_bytes(instance),builtin_catalog(),rule_set='park-baseline')
assert report['valid'] is False
assert any(d['code']=='endpoint_type_mismatch' for d in report['diagnostics'])
class MemoryPort:
    def __init__(self):self.state={}
    @contextmanager
    def transaction(self,scope):
        value=deepcopy(self.state.get(scope,{}))
        yield value
        self.state[scope]=value
store=MemoryPort()
core=builtin_catalog().export('core')
templates=Catalog(core['modules'])
roles={'editor':{'read','read_private','edit','submit'},'reviewer':{'read','read_private','review'},
       'publisher':{'read','publish'},'reader':{'read'}}
def workspace(actor):
    return DefinitionWorkbench(store,'synthetic',actor,templates=templates,
        authorize=lambda s,a,action:s=='synthetic' and action in roles.get(a,set()))
editor,reviewer,publisher,reader=(workspace(actor) for actor in roles)
editor.change(dict(action='save',request_id='a'*32,module_id='core',expected_revision=0,bundle=core,base_reference=None))
editor.change(dict(action='submit',request_id='b'*32,module_id='core',expected_revision=1))
assert reviewer.read('core')['reviews'][0]['can_decide']
assert reader.read('core')['draft'] is None and not reader.read('core')['reviews']
reviewer.change(dict(action='decide',request_id='c'*32,review_id='b'*32,decision='approved',reason='synthetic smoke only'))
release=publisher.change(dict(action='publish',request_id='d'*32,review_id='b'*32,expected_revision=1))
assert reader.definition(release['reference'])['modules'][0]['reference']==release['reference']
assert reader.released_library()['modules'][0]['published_at']==release['published_at']
assert 'sqlite3' not in sys.modules
catalog=builtin_catalog()
subset=catalog.export('electrical')
assert len(subset['modules'])==2
assert Catalog.from_bytes(canonical_bytes(subset)).export()==subset
assert vxture_ontology.__file__.startswith(sys.argv[1])
assert not any(name=='packages' or name.startswith(('fastapi','pydantic','numpy','sqlalchemy')) for name in sys.modules)
print(json.dumps({'modules':len(catalog.describe()['modules']),'isolated_wheel':True}))
'''
    with TemporaryDirectory(prefix='ontology-package-') as temporary:
        fixture = (Path(__file__).resolve().parents[2] / 'examples/ontology/parks/manufacturing.json').read_text(encoding='utf-8')
        result = subprocess.run([sys.executable, '-I', '-S', '-c', script, str(wheel)],
                                cwd=temporary, input=fixture, encoding='utf-8', capture_output=True, check=True)
        print(result.stdout.strip())
    subprocess.run([sys.executable, '-I', '-S', str(Path(__file__).with_name('smoke_ontology_host.py').resolve()),
                    str(wheel)], check=True)


if __name__ == '__main__':
    main()
