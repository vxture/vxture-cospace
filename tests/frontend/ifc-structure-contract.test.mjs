import assert from 'node:assert/strict';
import test from 'node:test';
import {checked} from '../../apps/workbench/src/layout/ifc-structure-contract.ts';

const space='space-1111111111111111',pin='a'.repeat(64);
function sample(){return {
 profile:'cospace.ifc-structure-view/0.1',space_id:space,catalog_sha256:pin,configured:true,
 data_kind:'ifc_design_candidate',assessment:'unverified',unit:'m',alignment_verified:false,
 ontology_bound:false,real_release_ready:false,geometry_integrity_checked:false,confirmed_connections:[],
 structure_available:true,entities:[{entity_id:'door',element_id:'e00001',name:'Door',ifc_type:'IfcDoor',source_role:'door',geometry_status:'extracted'}],
 relations:[],declared_role_counts:{door:1},
};}
test('pinned declarations remain separate from adopted facts',()=>{
 assert.equal(checked(sample(),space,pin).entities[0].entity_id,'door');
 for(const change of [{space_id:'other'},{catalog_sha256:'b'.repeat(64)},{alignment_verified:true},
  {ontology_bound:true},{real_release_ready:true},{confirmed_connections:[{}]},{data_kind:'real'}]){
  assert.throws(()=>checked({...sample(),...change},space,pin));
 }
});
test('rejects broken geometry references and fabricated summary counts',()=>{
 const value=sample();
 assert.throws(()=>checked({...value,entities:[...value.entities,...value.entities]},space,pin));
 assert.throws(()=>checked({...value,entities:[{...value.entities[0],element_id:'../mesh'}]},space,pin));
 assert.throws(()=>checked({...value,relations:[{ifc_relation_id:'rel',kind:'fills',source_id:'door',target_id:'missing'}]},space,pin));
 for(const counts of [{door:2},{door:1,space:0},[],{door:NaN}]){
  assert.throws(()=>checked({...value,declared_role_counts:counts},space,pin));
 }
});
test('legacy catalogs can explicitly have no declarations',()=>{
 const value={...sample(),structure_available:false,entities:[],relations:[],declared_role_counts:{}};
 assert.equal(checked(value,space,pin).structure_available,false);
});
