import json
import pytest
from test_preview_workflow import prepared
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from packages.ontology.scene_usage import usage, UsageQuery


class Allowed:
    def require(self,*args):pass


def test_fixed_references_scope_pagination_and_metadata_only(tmp_path,monkeypatch):
    _,jobs,directory,spaces,store,_,old,new=prepared(tmp_path)
    ref=jobs.model(new['candidate_id']).manifest['semantic_annotation']['ontology_ref']
    query=UsageQuery(space_id=spaces[0]['id'],**ref,limit=1)
    monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('must not poll'))
    monkeypatch.setattr(jobs,'model',lambda *a:pytest.fail('must not load model'))
    report=usage(jobs,directory,Allowed(),None,store,query)
    assert report['status']=='ready' and report['total']>=2 and report['next_offset']==1
    rows=[]
    for offset in range(report['total']):
        page=usage(jobs,directory,Allowed(),None,store,query.model_copy(update={'offset':offset}))
        rows.extend(page['items'])
    assert {r['kind'] for r in rows}=={'candidate','publication'}
    assert any(r['id']==new['id'] for r in rows)
    assert not any(r['id']==old['id'] for r in rows)
    assert all(r['ontology_ref']==ref and spaces[0]['id'] in r['href'] for r in rows)
    empty=usage(jobs,directory,Allowed(),None,store,query.model_copy(update={'space_id':spaces[1]['id']}))
    assert empty['status']=='ready' and empty['items']==[] and empty['total']==0


def test_partial_for_corrupt_metadata_and_budget_no_foreign_details(tmp_path,monkeypatch):
    _,jobs,directory,spaces,store,_,_,new=prepared(tmp_path)
    ref=jobs.model(new['candidate_id']).manifest['semantic_annotation']['ontology_ref']
    query=UsageQuery(space_id=spaces[0]['id'],**ref)
    path=jobs.root/'build-corrupt';path.mkdir();(path/'job.json').write_bytes(b'broken')
    report=usage(jobs,directory,Allowed(),None,store,query)
    assert report['status']=='partial' and 'build-corrupt' not in json.dumps(report)
    monkeypatch.setattr('packages.ontology.scene_usage.MAX_RECORDS',0)
    report=usage(jobs,directory,Allowed(),None,store,query)
    assert report['status']=='partial' and report['items']==[]


def test_denies_before_reading_rules_or_metadata(tmp_path):
    class Denied:
        def require(self,*args):raise PermissionError()
    class NoRules:
        def read(self,*args):pytest.fail('must authorize first')
    query=UsageQuery(space_id='space-'+'a'*16,ontology_id='x',version='1',sha256='a'*64)
    with pytest.raises(PermissionError):usage(None,None,Denied(),None,NoRules(),query)


@pytest.mark.parametrize('user,status',[('usr_local_test',403),('usr_other',403),('usr_engineer',409),('usr_manager',409)])
def test_http_permissions_and_strict_query(secured,user,status):
    _,client,_,_,_,_,spaces,*_=secured
    query={'space_id':spaces[0]['id'],'ontology_id':'missing','version':'1','sha256':'a'*64}
    assert client.get('/api/ontology-usage',params=query).status_code==401
    sign_in(secured,user)
    assert client.get('/api/ontology-usage',params=query).status_code==status
    assert client.get('/api/ontology-usage',params=query|{'space_id':spaces[1]['id']}).status_code==403
    assert client.post('/api/ontology-usage',json=query).status_code==403
    if status==409:
        assert client.get('/api/ontology-usage',params=query|{'unexpected':'x'}).status_code==422


def test_http_fixed_reference_revocation_and_no_scope_fallback(secured):
    _,client,_,_,jobs,_,spaces,policies,_,new=secured
    ref=jobs.model(new['candidate_id']).manifest['semantic_annotation']['ontology_ref']
    query={'space_id':spaces[0]['id'],**ref}
    sign_in(secured,'usr_engineer')
    response=client.get('/api/ontology-usage',params=query)
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    assert any(r['id']==new['id'] for r in response.json()['items'])
    assert client.get('/api/ontology-usage',params=query|{'sha256':'0'*64}).status_code==409
    assert client.get('/api/ontology-usage',params=list(query.items())+[('space_id',spaces[1]['id'])]).status_code==403
    revision,policy=policies.load();value=policy.model_dump()
    value['grants']=[g for g in value['grants'] if g['subject']!='usr_engineer']
    from packages.service.space_access import SpaceAccessPolicy
    policies.replace(SpaceAccessPolicy.model_validate(value),expected_revision=revision,actor='test',reason='revoke')
    assert client.get('/api/ontology-usage',params=query).status_code==403
