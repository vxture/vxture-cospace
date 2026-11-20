from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import pytest
from packages.ontology.group_configuration import GroupConfigurationStore, GroupConfigurationError, validate_change


def change(**patch):
    return dict(request_id='a'*32,expected_revision=0,group_id=None,name='实验室',description='专业分组',status='active',sort_order=90,reason='新增专业分类') | patch


def test_presets_are_stable_and_configuration_does_not_create_instances(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    result=store.read('scope')
    assert result['revision']==0 and len(result['groups'])==7
    assert all(g['origin']=='preset' and g['status']=='active' for g in result['groups'])
    assert store.read('other')==result
    assert not list(tmp_path.glob('*.json'))


def test_create_edit_disable_reactivate_history_and_persistence(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    created=store.change('scope','actor',change())
    group=next(g for g in created['groups'] if g['origin']=='custom')
    identity=group['group_id']
    disabled=store.change('scope','actor',change(request_id='b'*32,expected_revision=1,group_id=identity,name='研发实验室',status='inactive',reason='范围调整'))
    assert disabled['revision']==2
    assert disabled['history'][0]['before']['name']=='实验室'
    assert disabled['history'][0]['after']['status']=='inactive'
    assert disabled['history'][0]['actor']=='actor'
    assert disabled['history'][0]['reason']=='范围调整'
    assert GroupConfigurationStore(tmp_path).read('scope')==disabled
    active=store.change('scope','actor',change(request_id='c'*32,expected_revision=2,group_id=identity,status='active'))
    assert active['revision']==3 and len(active['groups'])==8
    assert store.read('other')['revision']==0


def test_idempotency_conflicting_retry_and_stale_revision(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    first=store.change('scope','actor',change())
    assert store.change('scope','actor',change())==first
    for patch,code in [({'reason':'changed'},'request_conflict'),({'request_id':'b'*32},'revision_changed')]:
        with pytest.raises(GroupConfigurationError,match=code):store.change('scope','actor',change(**patch))
    assert store.read('scope')['revision']==1


def test_duplicate_normalized_names_and_immutable_preset_name(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    store.change('scope','actor',change(name='ＡＢＣ'))
    with pytest.raises(GroupConfigurationError,match='name_exists'):
        store.change('scope','actor',change(request_id='b'*32,expected_revision=1,name='abc'))
    with pytest.raises(GroupConfigurationError,match='preset_name_fixed'):
        store.change('scope','actor',change(request_id='b'*32,expected_revision=1,group_id='preset-water',name='new'))
    updated=store.change('scope','actor',change(request_id='b'*32,expected_revision=1,group_id='preset-water',name='给排水',status='inactive'))
    assert updated['history'][0]['after']['origin']=='preset'


@pytest.mark.parametrize('patch',[{'name':'  '},{'name':'a\x00b'},{'description':'x'*501},{'expected_revision':True},{'sort_order':-1},{'sort_order':1.5},{'status':'deleted'},{'group_id':'../oops'},{'request_id':'wrong'},{'reason':''},{'scope':'spoofed'}])
def test_invalid_change_is_rejected(patch):
    with pytest.raises(GroupConfigurationError):validate_change(change(**patch))


def test_concurrent_changes_do_not_overwrite_each_other(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    store.read('scope')
    def run(i):
        try:return store.change('scope','actor',change(request_id=str(i)*32,name='group '+str(i)))['revision']
        except GroupConfigurationError as exc:return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[1,2]))
    assert sorted(map(str,results))==['1','ontology_group_revision_changed']
    assert store.read('scope')['revision']==1


def test_corrupt_state_never_falls_back_to_presets(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    store.change('scope','actor',change())
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE configuration SET groups_json='[]'")
    with pytest.raises(GroupConfigurationError,match='configuration_invalid'):store.read('scope')


def test_unknown_id_and_client_origin_are_rejected(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    with pytest.raises(GroupConfigurationError,match='not_found'):
        store.change('scope','actor',change(group_id='group-'+'b'*32))
    with pytest.raises(GroupConfigurationError):store.change('scope','actor',change(origin='preset'))

@pytest.mark.parametrize('direction,expected_index',[('top',0),('up',2),('down',4),('bottom',6)])
def test_four_moves_are_atomic_audited_and_idempotent(tmp_path,direction,expected_index):
    store=GroupConfigurationStore(tmp_path)
    before=store.read('scope')
    target=before['groups'][3]
    request=dict(request_id='b'*32,expected_revision=0,group_id=target['group_id'],move=direction,reason='调整分组顺序')
    result=store.change('scope','actor',request)
    assert result['groups'][expected_index]['group_id']==target['group_id']
    assert len({g['group_id'] for g in result['groups']})==7
    assert len({g['sort_order'] for g in result['groups']})==7
    assert result['revision']==1
    assert result['history'][0]['before']['sequence']==[{'group_id':g['group_id'],'name':g['name']} for g in before['groups']]
    assert result['history'][0]['after']['sequence']==[{'group_id':g['group_id'],'name':g['name']} for g in result['groups']]
    assert store.change('scope','actor',request)==result
    assert store.read('scope')==result


def test_move_boundaries_stale_revision_and_invalid_direction(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    initial=store.read('scope')
    request=dict(request_id='a'*32,expected_revision=0,group_id=initial['groups'][0]['group_id'],move='up',reason='move')
    assert store.change('scope','actor',request)['revision']==0
    store.change('scope','actor',dict(request,move='bottom'))
    with pytest.raises(GroupConfigurationError,match='revision_changed'):store.change('scope','actor',dict(request,request_id='b'*32))
    with pytest.raises(GroupConfigurationError,match='invalid_request'):store.change('scope','actor',dict(request,move='left'))


def test_edit_cannot_override_order_and_new_groups_append(tmp_path):
    store=GroupConfigurationStore(tmp_path)
    result=store.change('scope','actor',change(sort_order=0))
    assert result['groups'][-1]['origin']=='custom'
    group=result['groups'][-1]
    result=store.change('scope','actor',change(group_id=group['group_id'],request_id='b'*32,expected_revision=1,sort_order=0,name='改名'))
    assert result['groups'][-1]['name']=='改名'
