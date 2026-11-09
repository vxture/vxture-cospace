import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spatialServices,filterSpatialServices,serviceResourcePath} from '../../apps/workbench/src/layout/spatial-service-contract.ts';

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
