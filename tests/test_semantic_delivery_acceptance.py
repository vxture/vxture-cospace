"""B06 release acceptance across authoring, publication and local consumption."""
from copy import deepcopy
import io
import json
from pathlib import Path
import zipfile

import pytest
from packages.ontology.kernel import builtin_catalog, canonical_bytes
from packages.service.fixed_semantic_consumption import FixedSemantics
from packages.service.object_semantic_artifact import freeze, preflight, MANIFEST, MEMBERS
from packages.service.ontology_definition_workbench import DefinitionWorkbench
from packages.service.scene_ontology_links import SceneOntologyLinks
from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
from packages.views.agent.preview_offline import sha
from test_fixed_semantic_consumption import publish
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_preview_offline import pack
from test_publication_semantic_adoption import PREFLIGHT
from test_scene_ontology_links import publish_core


def selected_publication(secured, query, revision, request_id):
    client=secured[1];headers,_=sign_in(secured,'usr_manager')
    source_sha256=query['source_sha256'];query={k:v for k,v in query.items() if k!='source_sha256'}
    selection=client.post(PREFLIGHT,headers=headers,json=query|{'semantic_selection':{
        'consumer_revision':revision,'source_manifest_sha256':source_sha256}})
    assert selection.status_code==200,selection.text
    current=client.get('/api/selection',params={'space_id':query['space_id']}).json()
    result=client.post('/api/publications',headers=headers,json=query|dict(expected_revision=current['revision'],
        request_id=request_id,semantic_selection=selection.json()['semantic_selection']))
    assert result.status_code==201,result.text
    return result.json()


def test_published_history_survives_edit_unlink_definition_upgrade_and_explicit_new_release(secured,tmp_path):
    rp,client,_,_,_,directory,_,_,_,_=secured
    old=publish(secured);url=old['preview_url'];summary=client.get(url+'api/semantics').json()
    identity=summary['objects'][0]['object_id'];query=dict(space_id=old['space_id'],candidate_id=old['candidate_id'])
    before=client.get(url+'api/semantics',params={'object_id':identity}).json()
    raw=client.get(url+'offline.zip').content;bundle=tmp_path/'old.zip';bundle.write_bytes(raw)
    consumer=PersistentPreviewConsumer.initialize(tmp_path/'consumer',old['space_id'])
    consumer.install(bundle,old['id'],sha(raw));consumer.activate(old['id'],sha(raw),0)
    def unchanged():
        assert client.get(url+'api/semantics',params={'object_id':identity}).json()==before
        assert client.get(url+'offline.zip').content==raw
        restored=PersistentPreviewConsumer(consumer.root).restore(old['id'],sha(raw),1)
        assert restored.semantics(identity)==before|dict(consumer_revision=1,package_sha256=sha(raw))
    headers,_=sign_in(secured,'usr_engineer')
    links=client.get('/api/scene-ontology-links',params=query).json()
    common=query|dict(source_sha256=links['source_sha256'],object_id=identity)
    attributes=common|dict(action='properties',expected_revision=2,request_id='1'*32,
        properties={'name':{'value':'updated for next release'}},valid_time=None,evidence_note='new manual basis')
    assert client.post('/api/scene-ontology-links',headers=headers,json=attributes).json()['revision']==3
    unchanged()
    remove=common|dict(action='remove',expected_revision=3,request_id='2'*32)
    assert client.post('/api/scene-ontology-links',headers=headers,json=remove).json()['revision']==4
    unchanged()
    manager,_=sign_in(secured,'usr_manager')
    refused=client.post(PREFLIGHT,headers=manager,json=query|{'semantic_selection':{
        'consumer_revision':4,'source_manifest_sha256':links['source_sha256']}})
    assert refused.status_code==409
    scope=json.dumps([rp.config.issuer,'org_mock','ws_mock'],separators=(',',':'))
    newer=publish_core(directory.root,scope,version='0.2.0',revision=1,base=before['claim']['reference'])
    unchanged()
    headers,_=sign_in(secured,'usr_engineer')
    attach=common|dict(action='set',expected_revision=4,request_id='3'*32,reference=newer,concept_id='physical_object')
    assert client.post('/api/scene-ontology-links',headers=headers,json=attach).json()['revision']==5
    assert client.post('/api/scene-ontology-links',headers=headers,json=attributes|{
        'expected_revision':5,'request_id':'4'*32}).json()['revision']==6
    new=selected_publication(secured,query|{'source_sha256':links['source_sha256']},6,'5'*32)
    viewed=client.get(new['preview_url']+'api/semantics',params={'object_id':identity}).json()
    assert viewed['revision']==6 and viewed['claim']['reference']==newer
    assert viewed['claim']['instance_properties']['name']['value']=='updated for next release'
    unchanged()


def _record(manifest,files,source,selection):
    return dict(id='preview-'+'a'*16,space_id=source['space_id'],candidate_id=source['candidate_id'],
        model_manifest_sha256=source['source_sha256'],source_model_sha256=source['source_model_sha256'],
        semantic_workspace_scope=manifest['workspace_scope'],semantic_selection=selection,
        semantic_artifact=dict(path=MANIFEST,artifact_id=manifest['artifact_id'],profile=manifest['profile']),
        files={name:dict(sha256=sha(raw),bytes=len(raw)) for name,raw in files.items()})


def _park(root,park):
    fixture=json.loads(Path('examples/ontology/parks',park+'.json').read_bytes())
    catalog=builtin_catalog();refs={r['module_id']:r for r in fixture['definition_refs']}
    editor=DefinitionWorkbench(root,'acceptance','editor',True).service
    reviewer=DefinitionWorkbench(root,'acceptance','reviewer',True).service
    for index,identity in enumerate(sorted(refs,key=lambda identity:(identity!='core',identity))):
        ids=iter(f'{index*4+i:032x}' for i in range(1,5))
        editor.save('acceptance','editor',next(ids),module_id=identity,expected_revision=0,bundle=catalog.export(identity))
        review=editor.submit('acceptance','editor',next(ids),module_id=identity,expected_revision=1)
        reviewer.decide('acceptance','reviewer',next(ids),review_id=review['review_id'],decision='approved',reason='synthetic fixture')
        assert editor.publish('acceptance','editor',next(ids),review_id=review['review_id'],expected_revision=1)['reference']==refs[identity]
    source=dict(space_id='scene-'+park,candidate_id='build-one',source_sha256='a'*64,
        source_model_sha256='b'*64,frame_id='local-'+park,unit='m',axes=['x','y','z'],
        objects=[{'object_id':e['id'],'properties':{'name':e['properties']['name']['value']}}
                 for e in fixture['entities']],
        relations=[dict(relation_id=a['id'],source_id=a['subject_id'],target_id=a['object_id']) for a in fixture['assertions']])
    service=SceneOntologyLinks(root,'acceptance','engineer',None);revision=0;request=iter(f'{i:032x}' for i in range(1,100))
    common={k:source[k] for k in ('space_id','candidate_id','source_sha256')}
    for entity in fixture['entities']:
        module,concept=entity['type'].split(':')
        service.change(source,common|dict(action='set',object_id=entity['id'],reference=refs[module],concept_id=concept,
            expected_revision=revision,request_id=next(request)));revision+=1
        service.change(source,common|dict(action='properties',object_id=entity['id'],
            properties={key:{k:v for k,v in p.items() if k in ('value','unit','quantity')} for key,p in entity['properties'].items()},
            valid_time=entity.get('valid_time'),evidence_note=fixture['evidence'][0]['description'],
            expected_revision=revision,request_id=next(request)));revision+=1
    for assertion in fixture['assertions']:
        module,definition=assertion['relation'].split(':')
        service.change(source,common|dict(action='relation_set',relation_id=assertion['id'],reference=refs[module],
            definition_id=definition,direction='forward',valid_time=assertion['valid_time'],
            evidence_note=fixture['evidence'][0]['description'],expected_revision=revision,request_id=next(request)));revision+=1
    selection,_=preflight(service,source,dict(consumer_revision=revision,source_manifest_sha256=source['source_sha256']))
    manifest,files=freeze(service,source,selection,'2026-11-21T00:00:00Z')
    return source,manifest,files,_record(manifest,files,source,selection)


@pytest.mark.parametrize('park',['research-office','manufacturing','logistics'])
def test_three_park_full_definition_closure_and_mapped_set_survive_fixed_admission(tmp_path,park):
    source,manifest,files,record=_park(tmp_path,park)
    fixed=FixedSemantics(record,files,source,source['objects'],source['relations'])
    coverage=fixed.summary()['coverage']
    assert coverage['linked_objects']==coverage['objects_total']==15
    assert coverage['mapped_relations']==coverage['relations_total']==17
    assert fixed.summary()['assessment']['professional_review']=='not_performed'
    for item in source['objects']:
        viewed=fixed.query(item['object_id'],'2026-11-21T00:00:00Z')
        assert viewed['claim']['evidence_note'] and viewed['attribute_report']['valid']
        assert viewed['relation_report']['valid']
        assert not viewed['model_location']['available']
    broken=deepcopy(files)
    definitions=json.loads(broken['definitions.json'])
    definitions['modules']=[m for m in definitions['modules'] if m['module_id']!='core']
    broken['definitions.json']=canonical_bytes(definitions)
    # Recompute all enclosing hashes: dependency semantics must still refuse.
    validation=json.loads(broken['validation.json']);validation['input_sha256']['definitions.json']=sha(broken['definitions.json'])
    broken['validation.json']=canonical_bytes(validation)
    manifest=deepcopy(manifest)
    for name in MEMBERS:manifest['members'][name].update(sha256=sha(broken[name]),bytes=len(broken[name]))
    broken[MANIFEST]=canonical_bytes(manifest)
    record=_record(manifest,broken,source,record['semantic_selection'])
    with pytest.raises(ValueError,match='missing_dependency'):
        FixedSemantics(record,broken,source,source['objects'],source['relations'])


@pytest.mark.parametrize('corruption',['report','object','duplicate','budget'])
def test_semantic_refusal_preserves_installed_reference_and_active_session(secured,tmp_path,corruption):
    client=secured[1];record=publish(secured);raw=client.get(record['preview_url']+'offline.zip').content
    bundle=tmp_path/'fixed.zip';bundle.write_bytes(raw)
    store=PersistentPreviewConsumer.initialize(tmp_path/'consumer',record['space_id'])
    store.install(bundle,record['id'],sha(raw));session=store.activate(record['id'],sha(raw),0)
    before=store.status();viewed=session.semantics()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:files={name:archive.read(name) for name in archive.namelist()}
    if corruption=='report':
        report=json.loads(files['validation.json']);report['attributes']['valid']=False
        files['validation.json']=canonical_bytes(report)
    elif corruption=='object':
        index=json.loads(files['object-index.json']);index['objects'][0]['name']='changed origin'
        files['object-index.json']=canonical_bytes(index)
    elif corruption=='duplicate':
        files['claims.json']=files['claims.json'][:-1]+b',"revision":2}'
    else:files['claims.json']+=b' '*8_388_608
    manifest=json.loads(files[MANIFEST])
    for name in MEMBERS:manifest['members'][name].update(sha256=sha(files[name]),bytes=len(files[name]))
    files[MANIFEST]=canonical_bytes(manifest)
    publication=json.loads(files['publication.json'])
    for name in (*MEMBERS,MANIFEST):publication['files'][name].update(sha256=sha(files[name]),bytes=len(files[name]))
    files['publication.json']=canonical_bytes(publication)
    package=json.loads(files['package.json'])
    for name in package['files']:package['files'][name].update(sha256=sha(files[name]),bytes=len(files[name]))
    files['package.json']=canonical_bytes(package);changed=pack(files);bundle.write_bytes(changed)
    with pytest.raises(ValueError):store.install(bundle,record['id'],sha(changed))
    assert store.status()==before and store.session() is session
    assert session.semantics()==viewed


def test_cross_workspace_rejects_publication_query_before_fixed_files(secured,monkeypatch):
    client=secured[1];record=publish(secured)
    secured[2].workspace='ws_other';sign_in(secured,'usr_manager')
    def forbidden(*args,**kwargs):raise AssertionError('workspace denial must precede publication I/O')
    monkeypatch.setattr('packages.service.preview_publications.PreviewPublications.read',forbidden)
    for suffix in ('api/semantics','api/semantics?object_id=ghost','offline.zip'):
        assert client.get(record['preview_url']+suffix).status_code==403
