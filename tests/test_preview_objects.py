import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from packages.ontology.preview_versions import PreviewOntologies
from packages.spatial.preview_objects import SemanticRequest
from packages.construction.preview_semantics import annotate,ObjectRulesFailed
from packages.construction.preview_model import PreviewModel,digest
from packages.service.preview_publications import PreviewPublications
from packages.views.agent.preview_offline import OfflinePreview,export_bundle,sha
from experiments.scripts.serve_nyu_flow_preview import create_app
from test_preview_space_flow import setup


def fixture(tmp_path):
    initial,jobs,directory,spaces=setup(tmp_path)
    root=jobs.root/'build-one';model=json.loads((root/'output/model.json').read_bytes())
    ownership={k:model[k] for k in ('space_id','project_id')}
    binding={'id':'input-fixture',**ownership}
    model['source']['input_binding']=binding
    human=root/'output/human.ply'
    human.write_text('ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 2\n')
    model['members']['human.ply']={'sha256':digest(human),'bytes':human.stat().st_size}
    model.update(quality={'grade':'unverified','semantic_annotation':'not_available'},human_view={'path':'human.ply'},limitations=['no_semantic_objects'])
    model['agent_view']['path']='agent.npz'
    for view in ('human_view','agent_view'):model[view]['source_model_sha256']=model['members']['spatial.npz']['sha256']
    (root/'output/model.json').write_text(json.dumps(model),encoding='utf-8')
    job=json.loads((root/'job.json').read_bytes());job.update(input_id=binding['id'],input_binding=binding)
    (root/'job.json').write_text(json.dumps(job),encoding='utf-8')
    store=PreviewOntologies(tmp_path/'ontologies');rule=store.register('configs/ontology/indoor-equipment-v0.1.json')
    body={'space_id':spaces[0]['id'],'base_candidate_id':'build-one',
          'base_manifest_sha256':digest(root/'output/model.json'),
          'ontology_ref':{k:rule[k] for k in ('ontology_id','version','sha256')},
          'objects':[{'object_id':'object-001','type_id':'room','properties':{'name':'流程测试标注，待核实'},'point_index':0}]}
    return initial,jobs,directory,spaces,store,body


def test_new_candidate_preserves_geometry_old_records_and_object_identity(tmp_path):
    _,jobs,_,_,store,body=fixture(tmp_path)
    original={p.name:p.read_bytes() for p in (jobs.root/'build-one/output').iterdir()}
    selected=jobs.selection(body['space_id'])
    record=annotate(jobs,store,SemanticRequest.model_validate(body))
    assert jobs.selection(body['space_id'])==selected
    assert {p.name:p.read_bytes() for p in (jobs.root/'build-one/output').iterdir()}==original
    current=jobs.model(record['id']);result=current.objects('object-001');obj=result['objects'][0]
    assert (current.root/'spatial.npz').read_bytes()==original['spatial.npz']
    assert obj['anchor_m']==[0.,0.,2.] and obj['confirmation']=='unverified'
    assert obj['evidence']['sha256']==current.manifest['members']['spatial.npz']['sha256']
    assert current.manifest['human_view']['objects_path']==current.manifest['agent_view']['objects_path']=='objects.json'
    saved=json.loads((current.root/'offline-checks.json').read_bytes())
    assert saved['surface']['model_id']==record['id'] and saved['semantic_objects']==current.objects()
    result['objects'][0]['properties']['name']='changed response'
    assert current.objects()['objects'][0]['properties']['name']!='changed response'
    assert not list(jobs.root.glob('.pending-*'))


@pytest.mark.parametrize('change',[
    lambda b,s:b.update(space_id=s[1]['id']),
    lambda b,s:b.update(base_manifest_sha256='0'*64),
    lambda b,s:b['ontology_ref'].update(sha256='0'*64),
    lambda b,s:b['objects'][0].update(point_index=999),
    lambda b,s:b['objects'][0].update(type_id='unknown'),
    lambda b,s:b['objects'][0].update(properties={}),
    lambda b,s:b['objects'].append(dict(b['objects'][0])),
])
def test_invalid_references_and_rules_leave_no_candidate(tmp_path,change):
    _,jobs,_,spaces,store,body=fixture(tmp_path)
    before=jobs.list();change(body,spaces)
    with pytest.raises(ValueError):annotate(jobs,store,SemanticRequest.model_validate(body))
    assert jobs.list()==before and not list(jobs.root.glob('.pending-*'))


def test_scoped_objects_online_offline_and_historical_publication(tmp_path):
    initial,jobs,directory,_,store,body=fixture(tmp_path)
    jobs.select('build-one',0,body['space_id']);pubs=PreviewPublications(jobs)
    old=pubs.publish('build-one',1,body['space_id'])
    old_files={p.name:p.read_bytes() for p in (pubs.root/old['id']).iterdir()}
    with TestClient(create_app(initial,jobs,space_directory=directory,ontologies=store)) as client:
        assert client.get(old['preview_url']+'api/objects').status_code==404
        assert client.post('/api/semantic-candidates',json=body,headers={'Origin':'https://example.com'}).status_code==403
        assert client.post('/api/semantic-candidates',json=body|{'confirmation':'confirmed'}).status_code==422
        assert client.post('/api/semantic-candidates',json=body|{'objects':[body['objects'][0]|{'point_index':True}]}).status_code==422
        response=client.post('/api/semantic-candidates',json=body);assert response.status_code==201,response.text
        record=response.json();model=jobs.model(record['id'])
        assert client.get(f"/candidates/{record['id']}/api/objects/object-001").json()['objects'][0]['anchor_m']==[0.,0.,2.]
        assert client.get(f"/candidates/{record['id']}/api/objects/missing").status_code==404
        chosen=jobs.select(record['id'],1,body['space_id']);new=pubs.publish(record['id'],chosen['revision'],body['space_id'])
        info=client.get(new['preview_url']+'offline.json').json()
        assert info['profile']=='cospace.preview-offline/0.2'
        assert {'objects.json','ontology.json'}<=set(info['contents'])
        raw=client.get(new['preview_url']+'offline.zip').content
        offline=OfflinePreview(raw,new['id'],sha(raw))
        assert offline.objects()==client.get(new['preview_url']+'api/objects').json()
        assert offline.objects('object-001')==client.get(new['preview_url']+'api/objects/object-001').json()
        assert offline.query([0,0,2])==client.post(new['query_url'],json={'point_m':[0,0,2]}).json()
        # Fixed publications carry their own rule snapshot, never read a mutable registry.
        (store.path(body['ontology_ref']['ontology_id'],body['ontology_ref']['version'])/'definition.json').write_bytes(b'changed registry')
        assert client.get(new['preview_url']+'api/objects').status_code==200
    assert {p.name:p.read_bytes() for p in (pubs.root/old['id']).iterdir()}==old_files


@pytest.mark.parametrize('kind',['anchor','view'])
def test_semantic_binding_recomputed_beyond_file_digest(tmp_path,kind):
    _,jobs,_,_,store,body=fixture(tmp_path)
    record=annotate(jobs,store,SemanticRequest.model_validate(body));root=jobs.root/record['id']/'output'
    manifest=json.loads((root/'model.json').read_bytes())
    if kind=='anchor':
        doc=json.loads((root/'objects.json').read_bytes());doc['objects'][0]['anchor_m']=[1,2,3]
        path=root/'objects.json';path.write_text(json.dumps(doc),encoding='utf-8')
        manifest['members']['objects.json']={'sha256':digest(path),'bytes':path.stat().st_size}
    else:manifest['agent_view']['objects_path']='other.json'
    (root/'model.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='object_anchor_mismatch|semantic_view_binding'):PreviewModel(root)


def test_annotation_revision_keeps_ids_and_old_version_content(tmp_path):
    _,jobs,_,_,store,body=fixture(tmp_path)
    first=annotate(jobs,store,SemanticRequest.model_validate(body));one=jobs.model(first['id'])
    before=one.objects()
    body.update(base_candidate_id=first['id'],base_manifest_sha256=digest(one.root/'model.json'))
    body['objects'][0]['properties']['name']='新标注名称，待核实'
    second=annotate(jobs,store,SemanticRequest.model_validate(body));two=jobs.model(second['id'])
    assert one.objects()==before and two.objects()['objects'][0]['object_id']=='object-001'
    assert two.objects()['annotation_id']!=one.objects()['annotation_id']
    assert two.objects()['objects'][0]['properties']['name']!='流程测试标注，待核实'
