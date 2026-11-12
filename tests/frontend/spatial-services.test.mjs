import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spatialServices,filterSpatialServices,serviceResourcePath} from '../../apps/workbench/src/layout/spatial-service-contract.ts';
import {serviceListHref,servicePageHref,entryServiceTab} from '../../apps/workbench/src/layout/service-workspace-contract.ts';

test('navigation opens global service lists, without scene or record context',()=>{
 for(const section of ['directory','offline','online','feedback','recipients']){
  assert.equal(serviceListHref(section),`/services?section=${section}`);
  const list=new URL(serviceListHref(section,{query:'园区 A&B',state:'unavailable'}),'http://local');
  assert.deepEqual([...list.searchParams.keys()],['section','q','status']);
  assert.equal(list.searchParams.get('q'),'园区 A&B');
  assert.equal(list.searchParams.has('space'),false);
 }
});

test('each global list enters the corresponding dimension of a scene service page',()=>{
 assert.equal(entryServiceTab('directory'),'overview');
 for(const section of ['online','offline','feedback','recipients'])assert.equal(entryServiceTab(section),section);
 const url=new URL(servicePageHref('offline','A&B / 空间','fixed&1'),'http://local');
 assert.equal(url.searchParams.get('space'),'A&B / 空间');
 assert.equal(url.searchParams.get('publication'),'fixed&1');
 assert.equal(url.searchParams.get('tab'),'offline');
});

test('scene tab navigation keeps the pinned publication and list return context',()=>{
 for(const tab of ['overview','online','offline','feedback','recipients']){
  const url=new URL(servicePageHref('directory','scene-a','fixed-a',tab,{query:'园区',state:'available'}),'http://local');
  assert.equal(url.searchParams.get('section'),'directory');
  assert.equal(url.searchParams.get('space'),'scene-a');
  assert.equal(url.searchParams.get('publication'),'fixed-a');
  assert.equal(url.searchParams.get('tab'),tab);
  assert.equal(url.searchParams.get('q'),'园区');
  assert.equal(url.searchParams.get('status'),'available');
  assert.equal(url.searchParams.has('job'),false);
 }
 const list=new URL(serviceListHref('directory',{query:'园区',state:'available'}),'http://local');
 assert.equal(list.searchParams.has('publication'),false);
 assert.equal(list.searchParams.has('space'),false);
});

const release=(id,state='active',date='2026-11-10T00:00:00Z')=>({id,created_at:date,lifecycle_state:state});
const scene=(capabilities,publications)=>({id:'space-a',name:'园区',project_name:'北方项目',capabilities,publications});
test('catalog exposes only granted operations and retains fixed versions',()=>{
 const values=spatialServices([scene(['space.preview','space.query'],[release('preview-a'),release('preview-old','paused')])]);
 assert.equal(values.length,4);
 assert.deepEqual([...new Set(values.map(v=>v.kind))],['preview','query']);
 assert.equal(values.filter(v=>v.available).length,2);
 assert.equal(spatialServices([scene(undefined,[release('preview-a')])]).length,0);
 assert.equal(spatialServices([scene(['space.preview'],[])]).length,0);
});
test('paused, retired and unknown lifecycle records never enable consumption',()=>{
 for(const state of ['paused','retired','unexpected',undefined]){
  const values=spatialServices([scene(['space.export'],[{...release('preview-a'),lifecycle_state:state}])]);
  assert.equal(values[0].available,false);
 }
});
test('filters combine query, capability and availability with newest versions first',()=>{
 const values=spatialServices([scene(['space.preview','space.export'],[release('preview-old','active','2026-10-01'),release('preview-new'),release('preview-paused','paused')])]);
 assert.equal(filterSpatialServices(values,'北方','offline','available')[0].release.id,'preview-new');
 assert.equal(filterSpatialServices(values,'preview-paused','all','unavailable').length,2);
 assert.equal(filterSpatialServices(values,'不存在','all','all').length,0);
 assert.equal(filterSpatialServices(values,'园区','preview','available').length,2);
});
test('resource addresses stay bound to the selected fixed publication',()=>{
 const values=spatialServices([scene(['space.preview','space.query','space.export'],[release('preview-a')])]);
 assert.deepEqual(values.map(serviceResourcePath),['/publications/preview-a/api/preview','/publications/preview-a/api/query-range','/publications/preview-a/offline.zip']);
});
import {serviceSpaces,selectedServiceVersion,sectionServices} from '../../apps/workbench/src/layout/spatial-service-contract.ts';

test('a space with three capabilities and three versions has one catalog entry',()=>{
 const groups=serviceSpaces(spatialServices([scene(['space.preview','space.query','space.export'],[release('a'),release('b'),release('c')])]));
 assert.equal(groups.length,1);
 assert.equal(groups[0].versions.length,3);
 assert.equal(groups[0].versions[0].services.length,3);
});

test('initial version uses newest active while explicit paused or removed versions never fall back',()=>{
 const groups=serviceSpaces(spatialServices([scene(['space.export'],[release('older','active','2026-10-01'),release('new-paused','paused','2026-11-09'),release('new-active','active','2026-11-08')])]));
 assert.equal(selectedServiceVersion(groups[0]).release.id,'new-active');
 assert.equal(selectedServiceVersion(groups[0],'new-paused').available,false);
 assert.equal(selectedServiceVersion(groups[0],'removed'),undefined);
 assert.equal(selectedServiceVersion(groups[0],'older').release.id,'older');
});

test('offline and online sections retain independently granted operations',()=>{
 for(const [capability,expected,other] of [['space.export','offline','online'],['space.query','online','offline']]){
  const group=serviceSpaces(spatialServices([scene([capability],[release('a')])]))[0];
  const version=selectedServiceVersion(group);
  assert.equal(sectionServices(version,expected).length,1);
  assert.equal(sectionServices(version,other).length,0);
  assert.equal(sectionServices(version,'feedback').length,0);
 }
});

test('every operation in a grouped version keeps its own space and publication binding',()=>{
 const first=scene(['space.preview','space.query','space.export'],[release('fixed-a')]);
 const second={...first,id:'space-b',publications:[release('fixed-b')]};
 const groups=serviceSpaces(spatialServices([first,second]));
 assert.equal(groups.length,2);
 for(const group of groups)for(const version of group.versions)for(const item of version.services){
  assert.equal(item.scene.id,group.scene.id);
  assert.equal(item.release.id,version.release.id);
  assert.ok(serviceResourcePath(item).includes(version.release.id));
 }
});

test('refresh with a newer release preserves a pinned version and revocation removes it',()=>{
 const before=serviceSpaces(spatialServices([scene(['space.query'],[release('old','active','2026-10-01')])]))[0];
 const pinned=selectedServiceVersion(before).release.id;
 const after=serviceSpaces(spatialServices([scene(['space.query'],[release('old','active','2026-10-01'),release('new')])]))[0];
 assert.equal(selectedServiceVersion(after,pinned).release.id,'old');
 assert.equal(selectedServiceVersion(after).release.id,'new');
 const revoked=serviceSpaces(spatialServices([scene(['space.query'],[release('new')])]))[0];
 assert.equal(selectedServiceVersion(revoked,pinned),undefined);
});
