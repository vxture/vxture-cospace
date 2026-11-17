import assert from 'node:assert/strict';
import test from 'node:test';
import {checkedJsonFile} from '../../apps/workbench/src/layout/checked-json-file.ts';
import {readMappingFile,mappingFile,mappingDocument,validateMappingTargets} from '../../apps/workbench/src/layout/ifc-mapping-file.ts';

const space='space-1111111111111111',pin='a'.repeat(64),ontology={ontology_id:'structure',version:'1.0.0',sha256:'b'.repeat(64)};
const rules={IfcWall:'wall',IfcDoor:'door'};
const read=v=>readMappingFile(JSON.stringify(v,null,2),space,pin);

test('exported mapping roundtrips without reordering rules or saving unrelated fields',()=>{
 const file=mappingFile(space,pin,{...ontology,title:'not part of the pin'},{...rules,IfcStair:''});
 assert.deepEqual(file.mapping.rules.map(r=>r.ifc_type),['IfcWall','IfcDoor']);
 assert.deepEqual(read(file),{ontology,rules:{IfcDoor:'door',IfcWall:'wall'}});
 assert.deepEqual(file.mapping.ontology_ref,ontology);
 assert.equal(mappingDocument(ontology,rules).profile,'cospace.ifc-ontology-mapping/0.1');
});
test('old proposals only supply rules, never old results or asserted verification',()=>{
 const old={profile:'cospace.ifc-structure-type-proposals/0.1',source:{space_id:space,catalog_sha256:pin,ifc_sha256:'c'.repeat(64)},
  mapping:mappingDocument(ontology,rules),entities:[{entity_id:'fabricated'}],ontology_bound:true,real_release_ready:true};
 const loaded=read(old);
 assert.deepEqual(loaded.rules,{IfcDoor:'door',IfcWall:'wall'});
 assert.equal(Object.hasOwn(loaded,'entities'),false);
 assert.equal(Object.hasOwn(loaded,'real_release_ready'),false);
});
test('rejects other scene/catalog, ambiguous rule sets, arbitrary types, incomplete pins and extra config fields',()=>{
 const base=mappingFile(space,pin,ontology,rules);
 for(const patch of [{profile:'other'},{source:{space_id:space,catalog_sha256:'0'.repeat(64)}},
  {source:{space_id:'space-2222222222222222',catalog_sha256:pin}},{adopted:true},{source:null},{mapping:null}])assert.throws(()=>read({...base,...patch}));
 for(const entries of [[],[...base.mapping.rules,base.mapping.rules[0]],[{ifc_type:'NotIfc',target_type_id:'wall'}],
  [{ifc_type:'IfcDoor',target_type_id:'../wall'}],[{ifc_type:'IfcDoor',target_type_id:'door',adopt:true}],Array(101).fill(base.mapping.rules[0])]){
  assert.throws(()=>read({...base,mapping:{...base.mapping,rules:entries}}));
 }
 assert.throws(()=>read({...base,mapping:{...base.mapping,ontology_ref:{...ontology,sha256:'bad'}}}));
 assert.throws(()=>read({...base,mapping:{...base.mapping,ontology_ref:{...ontology,title:'extra'}}}));
});
test('duplicate JSON keys, escaped aliases, nesting and byte budgets rejected',()=>{
 assert.throws(()=>checkedJsonFile('{"rules":1,"rul\\u0065s":2}',100));
 assert.throws(()=>checkedJsonFile('['.repeat(66)+'0'+']'.repeat(66),1000));
 assert.throws(()=>checkedJsonFile('"中文"',6));
 assert.throws(()=>checkedJsonFile('{broken',100));
 assert.deepEqual(checkedJsonFile('{"a":[{"b":"comma,:\\\""},true,null,-1.2e+3]}',1000),{a:[{b:'comma,:"'},true,null,-1200]});
 assert.deepEqual(checkedJsonFile('{"a":{},"b":[]}',1000),{a:{},b:[]});
});
test('targets must be own declared types of reloaded fixed ontology',()=>{
 assert.doesNotThrow(()=>validateMappingTargets(rules,{door:{},wall:{}}));
 assert.throws(()=>validateMappingTargets(rules,{door:{}}));
 assert.throws(()=>validateMappingTargets({IfcDoor:'toString'},{}));
});
