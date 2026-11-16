import assert from 'node:assert/strict';
import test from 'node:test';
import {checked} from '../../apps/workbench/src/layout/ifc-observation-contract.ts';

const space='space-1111111111111111',pin='a'.repeat(64),element='e00001';
const sample=()=>({profile:'cospace.ifc-opening-observation-view/0.1',space_id:space,catalog_sha256:pin,element_id:element,
 data_kind:'ifc_design_candidate',assessment:'unverified',catalog_content_verified:true,source_content_verified:false,
 evidence_content_verified:false,clock_quality_verified:false,real_release_ready:false,configured:false,status:'unavailable',
 value:null,reported_at:null,active_count:0});
test('unconfigured reporting is separate from normal, reported and expired states',()=>{
 assert.equal(checked(sample(),space,pin,element).configured,false);
 for(const status of ['unavailable','expired','retracted','unknown','conflict']){
  assert.equal(checked({...sample(),configured:true,status},space,pin,element).value,null);
 }
 assert.equal(checked({...sample(),configured:true,status:'reported',value:'open',active_count:1},space,pin,element).value,'open');
});
test('rejects unbound, fabricated or misleading observation summaries',()=>{
 for(const change of [{space_id:'other'},{catalog_sha256:'b'.repeat(64)},{element_id:'e00002'},
  {source_content_verified:true},{evidence_content_verified:true},{clock_quality_verified:true},{real_release_ready:true},
  {status:'normal'},{status:'reported',value:'open'},{status:'expired',value:'closed'},
  {status:'reported',configured:true,value:'traversable'},{reported_at:'yesterday'},{active_count:-1}]){
  assert.throws(()=>checked({...sample(),...change},space,pin,element));
 }
});
