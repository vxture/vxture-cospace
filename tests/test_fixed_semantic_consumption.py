from copy import deepcopy
import io
import json
import socket
import zipfile

import pytest
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_publication_semantic_adoption import seed,PREFLIGHT
from test_preview_offline import pack
from test_object_semantic_artifact import prepare
from packages.service.object_semantic_artifact import freeze,MANIFEST,MEMBERS
from packages.service.fixed_semantic_consumption import FixedSemantics
from packages.views.agent.preview_offline import OfflinePreview,sha


def publish(secured):
    _,client,_,_,_,_,_,_,_,_=secured
    query,choice=seed(secured)
    headers,_=sign_in(secured,'usr_manager')
    selection=client.post(PREFLIGHT,headers=headers,json=query|{'semantic_selection':choice}).json()['semantic_selection']
    current=client.get('/api/selection',params={'space_id':query['space_id']}).json()
    response=client.post('/api/publications',headers=headers,json=query|dict(expected_revision=current['revision'],
        request_id='8'*32,semantic_selection=selection))
    assert response.status_code==201,response.text
    return response.json()


def test_online_offline_same_fixed_query_without_consumer_database_or_network(secured,monkeypatch):
    _,client,_,_,_,directory,_,_,old,_=secured
    record=publish(secured)
    url=record['preview_url']
    summary=client.get(url+'api/semantics')
    assert summary.status_code==200,summary.text
    assert summary.headers['cache-control']=='no-store'
    summary=summary.json();obj=summary['objects'][0]['object_id']
    viewed=client.get(url+'api/semantics',params={'object_id':obj}).json()
    assert viewed['claim']['instance_properties']['name']['value']=='verified format, unverified field'
    assert not viewed['model_location']['available']
    assert viewed['included_in_publication'] and viewed['relation_report'] is None
    assert client.get(old['preview_url']+'api/semantics').json()['state']=='not_included'
    assert client.get(old['preview_url']+'api/semantics?object_id='+obj).status_code==404
    assert client.get(url+'api/semantics?object_id='+obj+'&at=bad').status_code==422
    assert client.get(url+'api/semantics?object_id=a&object_id=b').status_code==403
    assert client.get(url+'api/semantics?at=2026-11-20T00:00:00Z').status_code==422
    info=client.get(url+'offline.json').json()
    assert info['profile']=='cospace.preview-offline/0.5' and info['semantic_artifact']=='included'
    downloaded=client.get(url+'offline.zip')
    assert downloaded.status_code==200
    raw=downloaded.content
    assert info['sha256']==sha(raw)
    assert raw==client.get(url+'offline.zip').content
    (directory.root/'scene-ontology-links.sqlite3').unlink()
    assert client.get(url+'api/semantics?object_id='+obj).json()==viewed
    def no_network(*args,**kwargs):raise AssertionError('offline must not access network')
    monkeypatch.setattr(socket,'socket',no_network)
    offline=OfflinePreview(raw,record['id'],sha(raw))
    assert offline.semantics()==summary
    assert offline.semantics(obj)==viewed
    for at in ('2026-11-20T00:00:00Z','2026-11-21T00:00:00Z'):
        assert offline.semantics(obj,at)['claim']['time_state']=='not_recorded'
    with pytest.raises(ValueError,match='invalid_query_time'):offline.semantics(obj,'bad')
    with pytest.raises(ValueError,match='invalid_semantic_query'):offline.semantics(at='2026-11-20T00:00:00Z')
    with pytest.raises(ValueError,match='object_not_found'):offline.semantics('ghost')


def test_semantic_profile_missing_members_and_self_consistent_false_coverage_rejected(secured):
    client=secured[1];record=publish(secured)
    raw=client.get(record['preview_url']+'offline.zip').content
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:files={name:archive.read(name) for name in archive.namelist()}
    bad=dict(files);del bad['definitions.json']
    changed=pack(bad)
    with pytest.raises(ValueError):OfflinePreview(changed,record['id'],sha(changed))
    manifest=json.loads(files[MANIFEST]);manifest['coverage']['linked_objects']+=1
    files[MANIFEST]=json.dumps(manifest).encode()
    pub=json.loads(files['publication.json'])
    pub['files'][MANIFEST]={'sha256':sha(files[MANIFEST]),'bytes':len(files[MANIFEST])}
    files['publication.json']=json.dumps(pub).encode()
    package=json.loads(files['package.json'])
    for name in (MANIFEST,'publication.json'):
        package['files'][name]={'sha256':sha(files[name]),'bytes':len(files[name])}
    files['package.json']=json.dumps(package).encode()
    changed=pack(files)
    with pytest.raises(ValueError,match='semantic_coverage_invalid'):
        OfflinePreview(changed,record['id'],sha(changed))


def test_fixed_semantics_requires_preview_permission_and_export_remains_separate(secured,monkeypatch):
    _,client,_,_,jobs,_,_,_,_,_=secured
    record=publish(secured)
    sign_in(secured,'usr_local_test')
    assert client.get(record['preview_url']+'api/semantics').status_code==200
    assert client.get(record['preview_url']+'offline.zip').status_code==403
    sign_in(secured,'usr_other')
    def forbidden(*args,**kwargs):raise AssertionError('permission before geometry')
    from packages.service.preview_publications import PreviewPublications
    monkeypatch.setattr(PreviewPublications,'read',forbidden)
    assert client.get(record['preview_url']+'api/semantics').status_code==403


def test_fixed_semantics_lifecycle_stops_new_reads_but_preserves_held_copy(secured):
    from packages.service.preview_publications import PreviewPublications
    from test_preview_control import run,payload
    _,client,_,_,jobs,_,_,_,_,_=secured
    record=publish(secured)
    pubs=PreviewPublications(jobs)
    url=record['preview_url'];key='publication:'+record['id']
    raw=client.get(url+'offline.zip').content
    held=OfflinePreview(raw,record['id'],sha(raw));expected=held.semantics()
    for operation in ('pause_distribution','restore','retire_publication'):
        if operation=='retire_publication':
            request=payload(jobs.controls,pubs,record['space_id'],key,operation)
            pubs.jobs.controls.change(pubs,request.model_copy(update={'retirement_kind':'erroneous'}))
        else:run(jobs.controls,pubs,record['space_id'],key,operation)
        if operation=='restore':
            assert client.get(url+'api/semantics').json()==expected
            assert client.get(url+'offline.zip').content==raw
        else:
            assert client.get(url+'api/semantics').status_code==409
            assert client.get(url+'offline.zip').status_code==409
        assert held.semantics()==expected


def test_offline_semantic_profile_cannot_downgrade_or_accept_unknown_members(secured):
    client=secured[1];record=publish(secured)
    raw=client.get(record['preview_url']+'offline.zip').content
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:files={name:archive.read(name) for name in archive.namelist()}
    package=json.loads(files['package.json']);package['profile']='cospace.preview-offline/0.4'
    files['package.json']=json.dumps(package).encode()
    changed=pack(files)
    with pytest.raises(ValueError,match='package_binding'):
        OfflinePreview(changed,record['id'],sha(changed))
    files['unexpected.json']=b'{}'
    changed=pack(files)
    with pytest.raises(ValueError,match='invalid_archive_members_or_size'):
        OfflinePreview(changed,record['id'],sha(changed))


def test_mapped_relation_rehydration_fixed_time_and_recomputed_reports(tmp_path):
    service,source,selection,_=prepare(tmp_path,True)
    manifest,files=freeze(service,source,selection,'2026-11-20T10:00:00Z')
    record=dict(id='preview-'+'a'*16,space_id=source['space_id'],candidate_id=source['candidate_id'],
        model_manifest_sha256=source['source_sha256'],source_model_sha256=source['source_model_sha256'],
        semantic_workspace_scope=manifest['workspace_scope'],semantic_selection=selection,
        semantic_artifact=dict(path=MANIFEST,artifact_id=manifest['artifact_id'],profile=manifest['profile']),
        files={name:{'sha256':sha(raw),'bytes':len(raw)} for name,raw in files.items()})
    fixed=FixedSemantics(record,files,{'frame_id':source['frame_id']},source['objects'],source['relations'])
    assert fixed.query('cabinet','2026-11-20T00:00:00Z')['relations'][0]['time_state']=='active'
    assert fixed.query('cabinet','2026-11-19T23:59:59Z')['relations'][0]['time_state']=='inactive'


def test_persistent_consumer_and_cli_restore_query_the_frozen_semantics(secured,tmp_path,monkeypatch,capsys):
    import sys
    from apps.cli.preview_consumer import main
    from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
    client=secured[1];record=publish(secured)
    summary=client.get(record['preview_url']+'api/semantics').json()
    obj=summary['objects'][0]['object_id']
    viewed=client.get(record['preview_url']+'api/semantics',params={'object_id':obj}).json()
    raw=client.get(record['preview_url']+'offline.zip').content
    bundle=tmp_path/'fixed.zip';bundle.write_bytes(raw)
    store=PersistentPreviewConsumer.initialize(tmp_path/'consumer',record['space_id'])
    store.install(bundle,record['id'],sha(raw))
    session=store.activate(record['id'],sha(raw),0)
    assert session.semantics()==summary|dict(consumer_revision=1,package_sha256=sha(raw))
    bundle.unlink()
    monkeypatch.setattr(socket,'socket',lambda *a,**k:pytest.fail('offline query must not use network'))
    args=['preview_consumer','--root',str(store.root),'restore','--publication',record['id'],
          '--sha256',sha(raw),'--expected-revision','1']
    capsys.readouterr()
    for suffix,expected in [(['--semantics'],summary),(['--semantics',obj],viewed)]:
        monkeypatch.setattr(sys,'argv',args+suffix);main()
        assert json.loads(capsys.readouterr().out)==expected|dict(consumer_revision=1,package_sha256=sha(raw))
    monkeypatch.setattr(sys,'argv',args+['--semantics','--at','2026-11-20T00:00:00Z'])
    with pytest.raises(SystemExit) as refused:main()
    assert refused.value.code==2
