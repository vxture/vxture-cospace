import pytest
from packages.ontology.resource_directory import ResourceDirectory, ResourceDirectoryError
from packages.ontology.kernel import builtin_catalog
from packages.ontology.group_configuration import GroupConfigurationStore


def directory(tmp_path):
    return ResourceDirectory(tmp_path,builtin_catalog().describe())


def test_seed_summary_filter_page_and_fixed_definition(tmp_path):
    store=directory(tmp_path)
    result=store.read('a',{'page_size':'3'})
    assert result['total']==8 and len(result['items'])==3
    assert all('definition' not in item for item in result['items'])
    rest=store.read('a',{'page_size':'3','page':'2','snapshot':result['snapshot']})
    assert not {i['reference']['module_id'] for i in result['items']} & {i['reference']['module_id'] for i in rest['items']}
    item=store.read('a',{'group':'preset-electrical'})['items'][0]
    assert item['reference']['module_id']=='electrical'
    assert store.read('a',{'group':'ungrouped'})['items'][0]['reference']['module_id']=='core'
    assert store.read('a',{'q':'额定电压'})['total']==1
    detail=store.definition(item['reference'])
    assert {e['reference']['module_id'] for e in detail['modules']}=={'core','electrical'}
    with pytest.raises(ResourceDirectoryError):store.definition({**item['reference'],'sha256':'0'*64})
    for query in ({'space_id':'forged'},{'page_size':'51'},{'page':'-1'},{'layer':'instance'},{'group':'missing'}):
        with pytest.raises(ResourceDirectoryError):store.read('a',query)


def test_membership_cas_isolation_idempotency_and_no_reseed(tmp_path):
    store=directory(tmp_path);before=store.read('a',{})
    body={'request_id':'a'*32,'module_id':'electrical','expected_revision':0,'group_ids':[]}
    assert store.change('a','actor',body)['revision']==1
    assert store.change('a','actor',body)['revision']==1
    assert store.read('a',{'group':'preset-electrical'})['total']==0
    assert directory(tmp_path).read('a',{'group':'ungrouped'})['total']==2
    assert store.read('b',{'group':'preset-electrical'})['total']==1
    with pytest.raises(ResourceDirectoryError,match='request_conflict'):store.change('a','other',body)
    with pytest.raises(ResourceDirectoryError,match='revision_changed'):store.change('a','actor',{**body,'request_id':'b'*32})
    with pytest.raises(ResourceDirectoryError,match='directory_changed'):store.read('a',{'snapshot':before['snapshot']})
    after=store.read('a',{})
    assert [i['reference'] for i in before['items']]==[i['reference'] for i in after['items']]


def test_inactive_existing_kept_but_new_link_rejected(tmp_path):
    config=GroupConfigurationStore(tmp_path)
    config.change('a','actor',{'request_id':'a'*32,'expected_revision':0,'group_id':'preset-electrical','name':'供配电','description':'','status':'inactive','sort_order':0,'reason':'停用'})
    store=directory(tmp_path)
    body={'request_id':'b'*32,'module_id':'electrical','expected_revision':0,'group_ids':['preset-electrical','preset-water']}
    store.change('a','actor',body)
    with pytest.raises(ResourceDirectoryError,match='group_inactive'):
        store.change('a','actor',{**body,'request_id':'c'*32,'module_id':'core','group_ids':['preset-electrical']})
    store.change('a','actor',{**body,'request_id':'d'*32,'expected_revision':1,'group_ids':[]})
    with pytest.raises(ResourceDirectoryError,match='group_inactive'):
        store.change('a','actor',{**body,'request_id':'e'*32,'expected_revision':2})


def test_custom_group_is_business_metadata_without_changing_definition(tmp_path):
    config=GroupConfigurationStore(tmp_path)
    result=config.change('a','actor',{'request_id':'f'*32,'expected_revision':0,'group_id':None,'name':'研发设施','description':'','status':'active','sort_order':0,'reason':'新建'})
    custom=next(g['group_id'] for g in result['groups'] if g['origin']=='custom')
    store=directory(tmp_path)
    reference=store.read('a',{'layer':'core'})['items'][0]['reference']
    store.change('a','actor',{'request_id':'a'*32,'module_id':'core','expected_revision':0,'group_ids':[custom]})
    assert store.read('a',{'group':custom})['items'][0]['reference']==reference
    assert custom not in {g['group_id'] for g in store.read('b',{})['groups']}
