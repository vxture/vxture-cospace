import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from packages.lifecycle.business_versions import BusinessVersions


def save(root, path, record):
    target = root/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record), encoding='utf-8')


def test_random_collision_concurrent_idempotency_and_growth(tmp_path):
    store = BusinessVersions(tmp_path)
    with patch('packages.lifecycle.business_versions.secrets.randbelow', side_effect=[7,7,8]):
        assert store.allocate('scene','','a','S',random_scene=True)=='S000007'
        assert store.allocate('scene','','b','S',random_scene=True)=='S000008'
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _:store.allocate('build','s','same','B'),range(16)))
    assert set(codes)=={'B01'}
    for i in range(2,101):
        assert store.allocate('build','s',str(i),'B')==f'B{i:02d}'
    assert BusinessVersions(tmp_path).lookup('build','s','same')=='B01'


def test_migration_lineage_and_estimated_times_do_not_rewrite_evidence(tmp_path):
    save(tmp_path,'preview-directory/space/space-a.json',{'id':'space-a','created_at':'2026-11-10T08:00:00+00:00'})
    base={'id':'build-a','space_id':'space-a','created_at':'2026-11-10T09:00:00+00:00',
          'started_at':'2026-11-10T09:01:00+00:00','finished_at':'2026-11-10T09:03:00+00:00','state':'succeeded'}
    save(tmp_path,'preview-builds/build-a/job.json',base)
    derived=base|{'id':'build-b','base_candidate_id':'build-a','created_at':'2026-11-10T09:10:00+00:00'}
    save(tmp_path,'preview-builds/build-b/job.json',derived)
    for i,candidate in enumerate(['build-a','build-b']):
        save(tmp_path,f'preview-builds/publications/preview-{i}/publication.json',
             {'id':f'preview-{i}','space_id':'space-a','candidate_id':candidate,'created_at':f'2026-11-10T09:{20+i}:00+00:00'})
    evidence={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    store=BusinessVersions(tmp_path);store.sync();store.sync()
    assert store.build_code('space-a','build-a')==store.build_code('space-a','build-b')=='B01'
    assert store.enrich('publication',{'id':'preview-1','space_id':'space-a','candidate_id':'build-b'})['version_code']=='B01-P02'
    assert store.estimate_demo_times()==2
    assert store.estimate_demo_times()==0
    stages=store.timeline('space-a','build-a')['stages']
    assert stages[2]=={'start':base['started_at'],'end':base['finished_at'],'estimated':False}
    assert stages[0]['estimated'] and stages[3]['estimated']
    assert all(stages[i]['end']==stages[i+1]['start'] for i in range(3))
    assert all(open(p,'rb').read()==raw for p,raw in evidence.items())


def test_missing_parent_and_inconsistent_dates_are_not_invented(tmp_path):
    save(tmp_path,'preview-directory/space/space-a.json',{'id':'space-a'})
    job={'id':'build-a','space_id':'space-a','base_candidate_id':'missing','state':'succeeded',
         'created_at':'2026-11-10T10:00:00+00:00','started_at':'2026-11-10T10:01:00+00:00',
         'finished_at':'2026-11-10T09:00:00+00:00'}
    save(tmp_path,'preview-builds/build-a/job.json',job)
    store=BusinessVersions(tmp_path);store.sync()
    assert store.build_code('space-a','build-a') is None
    assert store.estimate_demo_times()==0


def test_rule_versions_keep_original_protocol_and_workspace_scope(tmp_path):
    store=BusinessVersions(tmp_path)
    base={'ontology_id':'rooms','version':'1.0.0','sha256':'a'*64}
    first=store.ontology(base)
    assert first['version_code']=='O01-V01' and first['version']=='1.0.0'
    assert store.ontology(base)['version_code']==first['version_code']
    assert store.ontology(base|{'version':'1.1.0','sha256':'b'*64})['version_code']=='O01-V02'
    private=base|{'authoring':{'workspace':{'workspace_id':'other'}}}
    assert store.ontology(private)['version_code']=='O02-V01'


def test_display_codes_include_real_scene_prefix_without_replacing_local_codes(tmp_path):
    store = BusinessVersions(tmp_path)
    scene = store.allocate('scene', '', 'space-a', 'S', random_scene=True)
    store.allocate('build', 'space-a', 'build-a', 'B')
    store.allocate('publication', 'space-a/B01', 'pub-a', 'B01-P')
    build = store.enrich('build', {'id': 'build-a', 'space_id': 'space-a'})
    release = store.enrich('publication', {'id': 'pub-a', 'space_id': 'space-a', 'candidate_id': 'build-a'})
    assert build['build_code'] == 'B01'
    assert build['display_code'] == f'{scene}-B01'
    assert release['version_code'] == 'B01-P01'
    assert release['display_code'] == f'{scene}-B01-P01'
    assert release['build_display_code'] == build['display_code']
    unknown = store.enrich('build', {'id': 'unknown', 'space_id': 'unknown'})
    assert unknown['display_code'] is None
