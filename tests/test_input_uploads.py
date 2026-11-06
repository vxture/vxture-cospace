import io
import json
from pathlib import Path
import stat
import zipfile
import pytest
from packages.data.input_uploads import InputUploads,UploadRejected,unpack
from packages.data.preview_inputs import PreviewInputs
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.data.preview_preflight import preflight
from experiments.scripts.pack_input_upload import pack
from test_preview_inputs import source
from test_platform_business import secured,sign_in
from test_platform_login import runtime


def test_declared_upload_routes_match_supported_adapters_and_are_not_mutable():
    from packages.data.input_uploads import capabilities,FORMATS
    from packages.data.input_routes import route,routes
    info=capabilities()
    assert [r['format'] for r in info['routes']]==list(FORMATS)==info['formats']
    assert {r['category'] for r in info['routes']}=={'acquisition','existing_product'}
    assert all(r['requires'] and r['result'] and r['category_label'] for r in info['routes'])
    info['routes'][0]['requires'].clear()
    assert capabilities()['routes'][0]['requires']
    assert route('unknown') is None and routes(['unknown'])==[]


def catalog_at(tmp_path):
    directory=PreviewSpaces(tmp_path/'directory');project=directory.create('project','test')
    spaces=[directory.create('space',str(i),project['id'])['id'] for i in range(2)]
    return PreviewInputs(tmp_path/'catalog',directory),spaces


def package(tmp_path):
    snapshot,tracking=source(tmp_path);bundle=tmp_path/'sample.zip';pack(snapshot,tracking,bundle)
    return bundle


def test_upload_repeat_reopen_and_source_independent(tmp_path):
    bundle=package(tmp_path);catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    space=spaces[0]
    first=store.register(bundle,space,'短场景','engineer')
    second=InputUploads(PreviewInputs(catalog.root,catalog.directory)).register(bundle,space,'新名称不造版本','other')
    assert first['created'] and not second['created'] and first['input']['id']==second['input']['id']
    assert second['input']['label']=='短场景' and 'snapshot' not in first['input']
    assert first['input']['registration_ref']['actor']=='engineer'
    bundle.rename(tmp_path/'original-moved.zip')
    assert preflight(catalog,first['input']['id'])['status']=='passed'
    assert not list((catalog.root/'.upload-staging').iterdir())


def test_same_package_in_separate_scenes_gets_separate_records(tmp_path):
    bundle=package(tmp_path);catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    one=store.register(bundle,spaces[0],'one','actor')
    two=store.register(bundle,spaces[1],'two','actor')
    assert one['input']['id']!=two['input']['id'] and one['upload']['sha256']==two['upload']['sha256']


def test_copied_catalog_reuses_sealed_package_identity_and_description(tmp_path):
    import shutil
    from packages.data.input_descriptions import InputDescriptions,DescriptionChange
    bundle=package(tmp_path);catalog,spaces=catalog_at(tmp_path);space=spaces[0]
    original=InputUploads(catalog).register(bundle,space,'fixed original','actor')
    copied=PreviewInputs(tmp_path/'copied-catalog',catalog.directory)
    shutil.copy(catalog.root/(original['input']['id']+'.json'),copied.root)
    store=InputDescriptions(copied)
    saved=store.change(original['input']['id'],DescriptionChange(space_id=space,expected_revision=0,
        display_name='current display',description='',intended_use='',reason='rename'),'actor')
    repeat=InputUploads(copied).register(bundle,space,'do not overwrite','other')
    assert not repeat['created'] and repeat['input']['id']==original['input']['id']
    assert len(copied.list())==1 and not (copied.root/'uploads').exists()
    assert store.read(original['input']['id'],space)==saved
    record=catalog.read(original['input']['id']);(Path(record['snapshot'])/'raw/d.pgm').write_bytes(b'changed')
    with pytest.raises(UploadRejected,match='existing_evidence_invalid'):
        InputUploads(copied).register(bundle,space,'cannot silently repair','actor')


def test_ambiguous_package_records_are_not_silently_chosen(tmp_path):
    bundle=package(tmp_path);catalog,spaces=catalog_at(tmp_path)
    first=InputUploads(catalog).register(bundle,spaces[0],'original','actor');record=catalog.read(first['input']['id'])
    catalog.register('duplicate',record['snapshot'],record['tracking'],spaces[0],registration_ref=record['registration_ref'])
    with pytest.raises(UploadRejected,match='existing_records_ambiguous'):
        InputUploads(catalog).register(bundle,spaces[0],'ambiguous','actor')


@pytest.mark.parametrize('name',['../outside','/outside','D:/outside','snapshot/../outside','snapshot\\raw\\x.pgm','input.json/','INPUT.JSON','extra.txt'])
def test_unsafe_or_extra_zip_members_refused(tmp_path,name):
    bundle=tmp_path/'bad.zip'
    with zipfile.ZipFile(bundle,'w') as z:
        z.writestr('input.json','{}');z.writestr(name,'bad')
    with pytest.raises(UploadRejected):unpack(bundle,tmp_path/'expanded')
    assert not (tmp_path.parent/'outside').exists()


def test_links_and_expansion_budget_refused(tmp_path,monkeypatch):
    bundle=tmp_path/'bad.zip';info=zipfile.ZipInfo('input.json');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
    with zipfile.ZipFile(bundle,'w') as z:z.writestr(info,'/outside')
    with pytest.raises(UploadRejected,match='unsafe'):unpack(bundle,tmp_path/'expanded')
    monkeypatch.setattr('packages.data.input_uploads.MAX_EXPANDED',10)
    with zipfile.ZipFile(bundle,'w') as z:z.writestr('input.json','x'*11)
    with pytest.raises(UploadRejected,match='expanded_budget'):unpack(bundle,tmp_path/'expanded')


def test_invalid_package_leaves_no_record_or_retained_content(tmp_path):
    bundle=package(tmp_path);catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    raw=io.BytesIO()
    with zipfile.ZipFile(bundle) as z,zipfile.ZipFile(raw,'w') as target:
        for name in z.namelist():target.writestr(name,b'changed' if name.endswith('d.pgm') else z.read(name))
    bundle.write_bytes(raw.getvalue())
    with pytest.raises(UploadRejected,match='content_validation'):store.register(bundle,spaces[0],'bad','actor')
    assert store.catalog.list()==[] and not (store.catalog.root/'uploads').exists()
    assert not list((store.catalog.root/'.upload-staging').iterdir())


def test_storage_budget_and_metadata(tmp_path,monkeypatch):
    bundle=package(tmp_path);catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    monkeypatch.setattr('packages.data.input_uploads.MAX_SCENE_BYTES',1)
    with pytest.raises(UploadRejected,match='scene_storage'):store.register(bundle,spaces[0],'valid','actor')
    for scene,label in [('..','valid'),('space-'+'1'*16,' '),('space-'+'1'*16,'x'*101)]:
        with pytest.raises(UploadRejected):store.register(bundle,scene,label,'actor')


def test_http_upload_permissions_csrf_and_cross_scene(secured,tmp_path):
    _,c,_,_,jobs,_,spaces,*_=secured;bundle=package(tmp_path);query={'space_id':spaces[0]['id'],'label':'浏览器上传'}
    url='/api/input-uploads';headers={'Content-Type':'application/zip'};raw=bundle.read_bytes()
    assert c.post(url,params=query,content=raw,headers=headers).status_code==401
    viewer,_=sign_in(secured)
    assert c.post(url,params=query,content=raw,headers=viewer|headers).status_code==403
    assert c.get(url,params={'space_id':spaces[0]['id']}).status_code==403
    engineer,_=sign_in(secured,'usr_engineer')
    assert c.get(url,params={'space_id':spaces[0]['id']}).status_code==200
    assert c.post(url,params=query,content=raw,headers=headers).status_code==403
    assert c.post(url,params=query|{'space_id':spaces[1]['id']},content=raw,headers=engineer|headers).status_code==403
    response=c.post(url,params=query,content=raw,headers=engineer|headers)
    assert response.status_code==201,response.text
    result=response.json();assert result['input']['space_id']==spaces[0]['id']
    assert result['input']['registration_ref']['actor']=='usr_engineer'
    assert c.post(url,params=query,content=raw,headers=engineer|headers).json()['created'] is False
    assert c.post('/api/inputs/'+result['input']['id']+'/preflight',headers=engineer).json()['status']=='passed'


def test_http_bad_type_stream_budget_and_archive(secured,monkeypatch):
    _,c,*_=secured;headers,_=sign_in(secured,'usr_engineer');query={'space_id':secured[6][0]['id'],'label':'bad'}
    assert c.post('/api/input-uploads',params=query,content=b'bad',headers=headers).status_code==415
    h=headers|{'Content-Type':'application/zip'}
    assert c.post('/api/input-uploads',params=query,content=b'bad',headers=h).status_code==422
    monkeypatch.setattr('packages.service.platform_business_http.MAX_UPLOAD',3)
    assert c.post('/api/input-uploads',params=query,content=b'large',headers=h).status_code==413
    assert c.post('/api/input-uploads',params=query,content=iter([b'ab',b'cd']),headers=h).status_code==413


def test_interrupted_registration_reuses_fixed_content(tmp_path,monkeypatch):
    bundle=package(tmp_path);catalog,spaces=catalog_at(tmp_path);store=InputUploads(catalog)
    original=catalog.register
    def fail(*args,**kwargs):raise OSError('injected storage interruption')
    monkeypatch.setattr(catalog,'register',fail)
    with pytest.raises(OSError):store.register(bundle,spaces[0],'retry','actor')
    assert catalog.list()==[] and len(list((catalog.root/'uploads'/spaces[0]).iterdir()))==1
    monkeypatch.setattr(catalog,'register',original)
    result=store.register(bundle,spaces[0],'retry','actor')
    assert result['created'] and len(list((catalog.root/'uploads'/spaces[0]).iterdir()))==1


def test_concurrent_same_bundle_registers_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    bundle=package(tmp_path);catalog,spaces=catalog_at(tmp_path)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:InputUploads(catalog).register(bundle,spaces[0],'concurrent','actor'),range(2)))
    assert sum(r['created'] for r in results)==1 and len(catalog.list())==1


def test_revoked_during_upload_is_refused_before_registration(secured,tmp_path):
    from packages.service.space_access import SpaceAccessPolicy
    _,c,_,_,jobs,_,spaces,policies,*_=secured;headers,_=sign_in(secured,'usr_engineer')
    raw=package(tmp_path).read_bytes();before=len(jobs.inputs.list())
    def chunks():
        yield raw[:20]
        revision,_=policies.load()
        policies.replace(SpaceAccessPolicy.model_validate({'bindings':[],'grants':[]}),expected_revision=revision,actor='test',reason='revoke during body')
        yield raw[20:]
    result=c.post('/api/input-uploads',params={'space_id':spaces[0]['id'],'label':'revoked'},content=chunks(),headers=headers|{'Content-Type':'application/zip'})
    assert result.status_code==403,result.text
    assert len(jobs.inputs.list())==before


def test_manifest_schema_matches_runtime_formats(tmp_path):
    from jsonschema import Draft202012Validator
    from packages.data.input_uploads import FORMATS
    schema=json.loads(Path('contracts/schemas/input-upload-v0.1.schema.json').read_bytes())
    validator=Draft202012Validator(schema)
    assert schema['properties']['format']['enum']==list(FORMATS)
    for format in FORMATS:
        manifest={'profile':'cospace.input-upload/0.1','format':format}
        validator.validate(manifest)
        assert list(validator.iter_errors(manifest|{'space_id':'space-'+'1'*16}))
    assert list(validator.iter_errors({'profile':'cospace.input-upload/0.1','format':'arbitrary_bag'}))


@pytest.mark.parametrize('manifest',[
    '{"profile":"cospace.input-upload/0.1","format":"ros1_lidar_single_frame","format":"ros1_lidar_single_frame"}',
    '{"profile":"cospace.input-upload/0.1","format":"arbitrary_bag"}',
])
def test_duplicate_or_unsupported_manifest_refused(tmp_path,manifest):
    bundle=tmp_path/'bad.zip'
    with zipfile.ZipFile(bundle,'w') as archive:archive.writestr('input.json',manifest)
    expanded=tmp_path/'expanded';expanded.mkdir()
    with pytest.raises(UploadRejected):unpack(bundle,expanded)
