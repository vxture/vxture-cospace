import json
import sqlite3
import pytest
from packages.data.preflight_records import PreflightRecords
from packages.data.preview_preflight import preflight
from packages.service.space_access import SpaceAccessPolicy
from test_space_sources import sources_secured
from test_platform_business import secured, sign_in
from test_platform_login import runtime


def setup_history(fixture, count=5):
    secured, _, item=fixture
    store=PreflightRecords(secured[4].inputs)
    report=preflight(store.catalog,item['id'])
    for i in range(count):
        store.save(item['id'],report|{'status':'failed' if i%2 else 'passed'},'usr_engineer',store.fingerprint(item['id']))
    return secured,item,store,'/api/inputs/'+item['id']+'/preflight/history'


def test_history_cursor_survives_append_and_keeps_exact_identity(sources_secured,monkeypatch):
    secured,item,store,path=setup_history(sources_secured)
    client=secured[1];sign_in(secured,'usr_engineer')
    before=store.path.read_bytes()
    monkeypatch.setattr(store.catalog,'resolve',lambda *a:pytest.fail('history cannot inspect source files'))
    first=client.get(path,params={'limit':2}).json()
    assert [i['sequence'] for i in first['items']]==[5,4]
    assert first['next_before_sequence']==4 and not first['current_files_checked']
    assert before==store.path.read_bytes()
    store.save(item['id'],first['items'][0],'usr_engineer',store.fingerprint(item['id']))
    second=client.get(path,params={'limit':2,'before_sequence':4}).json()
    assert [i['sequence'] for i in second['items']]==[3,2]
    assert [i['sequence'] for i in client.get(path,params={'before_sequence':2}).json()['items']]==[1]
    exact=client.get(path,params={'sequence':2})
    assert exact.status_code==200 and exact.json()['items'][0]['status']=='failed'
    assert exact.json()['items'][0]['sequence']==2 and len(exact.json()['items'])==1
    assert client.get(path,params={'sequence':999}).json()['items']==[]
    assert client.get(path).headers['cache-control']=='no-store'


def test_history_empty_does_not_create_db_and_registration_change_is_explicit(sources_secured):
    secured,item,store,path=setup_history(sources_secured,0)
    client=secured[1];sign_in(secured,'usr_engineer')
    assert client.get(path).json()['items']==[] and not store.path.exists()
    store.save(item['id'],preflight(store.catalog,item['id']),'actor',store.fingerprint(item['id']))
    file=store.catalog.root/(item['id']+'.json')
    record=json.loads(file.read_bytes());record['label']='new registration label';file.write_text(json.dumps(record))
    saved=client.get(path).json()['items'][0]
    assert not saved['registration_matches'] and not saved['current_files_checked']


def test_history_authorizes_before_read_and_rechecks_revocation(sources_secured,monkeypatch):
    secured,item,store,path=setup_history(sources_secured)
    client=secured[1]
    assert client.get(path).status_code==401
    with monkeypatch.context() as patch:
        patch.setattr(PreflightRecords,'history',lambda *a,**k:pytest.fail('authorize before history'))
        sign_in(secured)
        assert client.get(path).status_code==403
        sign_in(secured,'usr_engineer')
        assert client.get(path,params={'space_id':secured[6][1]['id']}).status_code==403
    assert client.get(path).status_code==200
    revision,policy=secured[7].load()
    secured[7].replace(SpaceAccessPolicy(bindings=policy.bindings,grants=[]),expected_revision=revision,actor='test',reason='revoke')
    assert client.get(path).status_code==403


@pytest.mark.parametrize('query',[{'limit':0},{'limit':101},{'sequence':0},{'before_sequence':-1},
    {'sequence':9007199254740992},{'unknown':'1'},{'sequence':2,'before_sequence':3}])
def test_history_rejects_invalid_queries(sources_secured,query):
    secured,item,store,path=setup_history(sources_secured,0);client=secured[1];sign_in(secured,'usr_engineer')
    assert client.get(path,params=query).status_code==422
    assert client.get(path+'?limit=1&limit=2').status_code==403
    assert client.post(path).status_code==403


def test_history_corruption_never_becomes_empty_or_latest_fallback(sources_secured):
    secured,item,store,path=setup_history(sources_secured);client=secured[1];sign_in(secured,'usr_engineer')
    with sqlite3.connect(store.path) as db:
        db.execute('UPDATE checks SET record=? WHERE sequence=2',(json.dumps({'input_id':'foreign','status':'passed'}),))
    assert client.get(path,params={'sequence':2}).status_code==503
    assert client.get(path,params={'sequence':5}).json()['items'][0]['sequence']==5
    store.path.write_bytes(b'broken')
    assert client.get(path).status_code==503


def test_catalog_preflight_link_fixes_sequence(sources_secured):
    secured,item,store,path=setup_history(sources_secured);client=secured[1];sign_in(secured,'usr_engineer')
    row=next(i for i in client.get('/api/data-catalog').json()['items'] if i['kind']=='preflight')
    assert row['record_id']==item['id']+'@5' and 'check=5' in row['href']
    store.save(item['id'],preflight(store.catalog,item['id']),'actor',store.fingerprint(item['id']))
    assert client.get(path,params={'sequence':5}).json()['items'][0]['sequence']==5


def test_same_database_sequence_cannot_read_another_inputs_record(sources_secured):
    secured,item,store,path=setup_history(sources_secured)
    client=secured[1];sign_in(secured,'usr_engineer')
    other=store.catalog.register('second input',item['snapshot'],item['tracking'],item['space_id'])
    report=preflight(store.catalog,other['id'])
    saved=store.save(other['id'],report,'actor',store.fingerprint(other['id']))
    assert client.get(path,params={'sequence':saved['sequence']}).json()['items']==[]
    other_path='/api/inputs/'+other['id']+'/preflight/history'
    assert client.get(other_path,params={'sequence':1}).json()['items']==[]
    assert client.get(other_path).json()['items'][0]['input_id']==other['id']
