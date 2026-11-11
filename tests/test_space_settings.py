from concurrent.futures import ThreadPoolExecutor
import hashlib
import pytest
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.lifecycle.space_settings import SpaceSettingsChange, SettingsConflict, SettingsUnavailable
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def body(identity, **overrides):
    return dict(space_id=identity,expected_revision=0,name='Updated equipment room',
                description='Inspection equipment area',reason='Confirm room display name') | overrides


def test_metadata_overlay_atomic_history_restart_and_no_original_rewrite(tmp_path):
    directory=PreviewSpaces(tmp_path/'directory')
    project=directory.create('project','Project');space=directory.create('space','Original',project['id'])
    original=directory.root/'space'/(space['id']+'.json');before=original.read_bytes()
    assert directory.settings.read(space['id'])=={'revision':0,'history':[]}
    assert not directory.settings.path.exists()
    change=SpaceSettingsChange.model_validate(body(space['id']))
    result=directory.settings.change(change,'usr_manager',space)
    restarted=PreviewSpaces(directory.root);updated=restarted.read('space',space['id'])
    assert updated['name']==change.name and updated['project_id']==project['id']
    assert original.read_bytes()==before
    assert result['revision']==1 and result['history'][0]['actor']=='usr_manager'
    assert result['history'][0]['before']=={'name':'Original','description':''}
    assert restarted.settings.read(space['id'])==result
    with pytest.raises(SettingsConflict):directory.settings.change(change,'usr_manager',space)
    no_op=change.model_copy(update={'expected_revision':1})
    assert directory.settings.change(no_op,'usr_manager',space)==result


def test_concurrent_compare_and_swap_only_one_winner(tmp_path):
    d=PreviewSpaces(tmp_path/'directory');p=d.create('project','P');s=d.create('space','S',p['id'])
    # Initialize revision one, then race two independent local store instances.
    d.settings.change(SpaceSettingsChange.model_validate(body(s['id'])),'usr_a',s)
    def submit(name):
        try:
            store=PreviewSpaces(d.root).settings
            return store.change(SpaceSettingsChange.model_validate(body(s['id'],expected_revision=1,name=name)),'usr_a',s)['revision']
        except SettingsConflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,['Version A','Version B']))
    assert sorted(map(str,results))==['2','conflict']
    assert len(d.settings.read(s['id'])['history'])==2


def test_geographic_metadata_is_revisioned_and_preserved_by_older_clients(tmp_path):
    d=PreviewSpaces(tmp_path/'directory');p=d.create('project','P');s=d.create('space','S',p['id'])
    location={'longitude':116.39,'latitude':39.90,'crs':'WGS84'}
    d.settings.change(SpaceSettingsChange.model_validate(body(s['id'],address='北京',location=location)),'manager',s)
    assert d.read('space',s['id'])['location']==location
    d.settings.change(SpaceSettingsChange.model_validate(body(s['id'],expected_revision=1,name='Renamed')),'manager',d.read('space',s['id']))
    assert d.read('space',s['id'])['location']==location
    assert d.settings.read(s['id'])['history'][0]['after']['address']=='北京'
    d.settings.change(SpaceSettingsChange.model_validate(body(s['id'],expected_revision=2,location=None)),'manager',d.read('space',s['id']))
    assert d.read('space',s['id'])['location'] is None
    from pydantic import ValidationError
    for invalid in ({'longitude':181,'latitude':0,'crs':'WGS84'},{'longitude':0,'latitude':91,'crs':'GCJ02'},{'longitude':0,'latitude':0,'crs':'unknown'}):
        with pytest.raises(ValidationError):SpaceSettingsChange.model_validate(body(s['id'],location=invalid))


@pytest.mark.parametrize('user,can_manage',[('usr_local_test',False),('usr_engineer',False),('usr_manager',True)])
def test_settings_http_role_and_cross_space(secured,user,can_manage):
    _,c,_,_,_,directory,spaces,*_=secured;headers,_=sign_in(secured,user)
    identity=spaces[0]['id'];foreign=spaces[1]['id']
    response=c.get('/api/space-settings',params={'space_id':identity})
    assert response.status_code==200,response.text
    assert response.json()['can_manage'] is can_manage
    assert response.json()['history']==[]
    assert c.get('/api/space-settings',params={'space_id':foreign}).status_code==403
    r=c.post('/api/space-settings',json=body(identity),headers=headers)
    assert r.status_code==(200 if can_manage else 403),r.text
    assert c.post('/api/space-settings',json=body(foreign),headers=headers).status_code==403
    assert directory.settings.path.exists() is can_manage


def test_manager_real_updates_appear_in_directory_keep_releases_fixed_and_conflict(secured):
    _,c,_,_,jobs,directory,spaces,_,_,new=secured;headers,_=sign_in(secured,'usr_manager')
    def files():return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in jobs.root.rglob('*') if p.is_file()}
    before=files();identity=spaces[0]['id']
    location={'longitude':116.39,'latitude':39.90,'crs':'WGS84'}
    r=c.post('/api/space-settings',json=body(identity,address='北京 · 实验室',location=location),headers=headers);assert r.status_code==200,r.text
    data=r.json();assert data['revision']==1 and data['history'][0]['actor']=='usr_manager'
    assert data['space']['location']==location and data['space']['address']=='北京 · 实验室'
    assert next(s for s in c.get('/api/spaces').json()['spaces'] if s['id']==identity)['location']==location
    assert c.get('/api/spaces/'+identity).json()['name']=='Updated equipment room'
    assert next(s for s in c.get('/api/spaces').json()['spaces'] if s['id']==identity)['name']=='Updated equipment room'
    assert c.post('/api/space-settings',json=body(identity,name='stale'),headers=headers).status_code==409
    assert directory.read('space',identity)['name']=='Updated equipment room'
    sign_in(secured)
    read=c.get('/api/space-settings',params={'space_id':identity}).json()
    assert read['revision']==1 and read['history']==[] and not read['can_manage']
    assert files()==before


@pytest.mark.parametrize('overrides',[{'name':'  '},{'name':'x'*101},{'reason':''},{'expected_revision':True},
                                    {'project_id':'project-'+'f'*16},{'coordinate':'new frame'}])
def test_invalid_settings_do_not_mutate(secured,overrides):
    _,c,_,_,_,d,spaces,*_=secured;headers,_=sign_in(secured,'usr_manager')
    assert c.post('/api/space-settings',json=body(spaces[0]['id'],**overrides),headers=headers).status_code==403
    assert not d.settings.path.exists()


def test_settings_csrf_revocation_and_fail_closed_corrupt_store(secured):
    _,c,_,_,_,d,spaces,policies,*_=secured;headers,_=sign_in(secured,'usr_manager');identity=spaces[0]['id']
    assert c.post('/api/space-settings',json=body(identity)).status_code==403
    rev,policy=policies.load();value=policy.model_dump();value['grants']=[g for g in value['grants'] if g['subject']!='usr_manager']
    from packages.service.space_access import SpaceAccessPolicy
    policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=rev,actor='test',reason='revoke')
    assert c.post('/api/space-settings',json=body(identity),headers=headers).status_code==403
    sign_in(secured)
    d.settings.path.write_bytes(b'corrupt')
    assert c.get('/api/space-settings',params={'space_id':identity}).status_code==503
    assert c.get('/api/spaces').status_code==503
    with pytest.raises(SettingsUnavailable):d.read('space',identity)


def test_response_fields_and_revision_are_one_committed_snapshot(secured,monkeypatch):
    _,c,_,_,_,d,spaces,*_=secured;headers,_=sign_in(secured,'usr_manager')
    original=d.settings.change
    def concurrent_save(change,actor,record):
        committed=original(change,actor,record)
        original(change.model_copy(update={'expected_revision':committed['revision'],'name':'Later manager update'}),actor,record)
        return committed
    monkeypatch.setattr(d.settings,'change',concurrent_save)
    response=c.post('/api/space-settings',json=body(spaces[0]['id']),headers=headers)
    assert response.status_code==200,response.text
    saved=response.json()
    assert saved['revision']==1 and saved['space']['name']=='Updated equipment room'
    latest=c.get('/api/space-settings',params={'space_id':spaces[0]['id']}).json()
    assert latest['revision']==2 and latest['space']['name']=='Later manager update'


def test_altitude_round_trip_history_and_finite_validation(tmp_path):
    from pydantic import ValidationError
    d=PreviewSpaces(tmp_path/'directory');p=d.create('project','P');s=d.create('space','S',p['id'])
    location={'longitude':116.39,'latitude':39.90,'altitude':-12.5,'crs':'WGS84'}
    record=d.settings.change(SpaceSettingsChange.model_validate(body(s['id'],location=location)),'manager',s)
    assert PreviewSpaces(d.root).read('space',s['id'])['location']==location
    assert record['history'][0]['after']['location']['altitude']==-12.5
    for invalid in (float('nan'),float('inf')):
        with pytest.raises(ValidationError):
            SpaceSettingsChange.model_validate(body(s['id'],location=location|{'altitude':invalid}))
