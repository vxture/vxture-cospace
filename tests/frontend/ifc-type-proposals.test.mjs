import assert from 'node:assert/strict';
import test from 'node:test';
import {checkedTypeProposals} from '../../apps/workbench/src/layout/ifc-type-proposal-contract.ts';
const space='space-1111111111111111',pin='a'.repeat(64),ontology={ontology_id:'structure',version:'1.0.0',sha256:'b'.repeat(64)};
const sources=[{entity_id:'door',element_id:'e00001',ifc_type:'IfcDoor'}],rules={IfcDoor:'door'};
function sample(){return {profile:'cospace.ifc-structure-type-proposals/0.1',source:{space_id:space,catalog_sha256:pin},ontology_ref:ontology,
 mapping:{profile:'cospace.ifc-ontology-mapping/0.1',ontology_ref:ontology,rules:[{ifc_type:'IfcDoor',target_type_id:'door'}]},
 mapping_sha256:'c'.repeat(64),structure_sha256:'d'.repeat(64),data_kind:'ifc_design_candidate',assessment:'unverified',
 instance_validated:false,relationships_mapped:false,ontology_bound:false,alignment_verified:false,saved:false,real_release_ready:false,
 entities:[{source_entity_id:'door',element_id:'e00001',ifc_type:'IfcDoor',target_type_id:'door',status:'proposed'}],proposed_count:1,unmapped_count:0};}
const check=v=>checkedTypeProposals(v,space,pin,ontology,sources,rules);
test('type proposals match explicit source, ontology and rules',()=>{
 assert.equal(check(sample()).proposed_count,1);
 assert.throws(()=>checkedTypeProposals(sample(),space,pin,{...ontology,version:'2.0.0'},sources,rules));
 assert.throws(()=>checkedTypeProposals(sample(),space,pin,ontology,sources,{IfcDoor:'cabinet'}));
});
test('rejects source mismatch, promoted claims and fabricated rows',()=>{
 for(const change of [{source:{space_id:space,catalog_sha256:'x'}},{saved:true},{ontology_bound:true},{instance_validated:true},
  {relationships_mapped:true},{alignment_verified:true},{real_release_ready:true},{proposed_count:2},{entities:[]}])assert.throws(()=>check({...sample(),...change}));
 for(const change of [{element_id:'e00002'},{ifc_type:'IfcWall'},{target_type_id:'cabinet'},{status:'unmapped'},{source_entity_id:'missing'}]){
  assert.throws(()=>check({...sample(),entities:[{...sample().entities[0],...change}]}));
 }
});
test('unmapped remains explicit, never filled from a name or role',()=>{
 const value={...sample(),mapping:{...sample().mapping,rules:[]},entities:[{...sample().entities[0],target_type_id:null,status:'unmapped'}],proposed_count:0,unmapped_count:1};
 assert.equal(checkedTypeProposals(value,space,pin,ontology,sources,{}).unmapped_count,1);
});
import './ifc-mapping-file.test.mjs';
