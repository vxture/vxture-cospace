import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseWorkbench,bumpVersion,chooseDependency} from '../../packages/ontology-ui/src/authoring-contract.ts';

const definitions=JSON.parse(readFileSync('packages/ontology/kernel/definitions.json','utf8'));
const base=()=>({profile:'vxture.ontology-workbench/0.1',module_id:'core',can_manage:true,draft:null,source_bundle:structuredClone(definitions),releases:[],reviews:[],validation:null,comparison:null});
test('workbench contract accepts incomplete semantic references and rejects unusable forms',()=>{
 const value=base();value.source_bundle.modules[0].concepts.physical_object.parent='core:missing';assert.equal(parseWorkbench(value),value);
 for(const invalid of [null,{}, {...base(),can_manage:'yes'}, {...base(),reviews:Array(51).fill({})}])assert.throws(()=>parseWorkbench(invalid));
 const invalid=base();invalid.source_bundle.modules[0].concepts.entity.properties.name=null;assert.throws(()=>parseWorkbench(invalid));
 assert.equal(bumpVersion('0.2.0'),'0.3.0');
});
test('dependency choice explicitly updates pins and retains exact selected closure',()=>{
 const core=structuredClone(definitions.modules.find(m=>m.module_id==='core'));
 const electrical=structuredClone(definitions.modules.find(m=>m.module_id==='electrical'));
 const original={profile:definitions.profile,modules:[core,electrical]};const before=structuredClone(original);
 const next=structuredClone(core);next.version='0.2.0';const reference={module_id:'core',version:'0.2.0',sha256:'a'.repeat(64)};
 const changed=chooseDependency(original,'electrical',reference,{profile:definitions.profile,modules:[next]});
 assert.deepEqual(original,before);assert.equal(changed.modules[0].version,'0.2.0');assert.deepEqual(changed.modules[1].requires,[reference]);
 assert.throws(()=>chooseDependency(original,'electrical',{...reference,module_id:'unknown'},{profile:definitions.profile,modules:[next]}));
});
test('authoring UI keeps data in content and receives host transport only',()=>{
 const source=readFileSync('packages/ontology-ui/src/authoring.tsx','utf8');
 assert.doesNotMatch(source,/fetch\(|businessEndpoint|useNavigate|workspace_id|\/api\//);
 assert.match(source,/Drawer/);assert.match(source,/保存草稿/);assert.match(source,/查看送审定义/);
 assert.doesNotMatch(source,/window\.confirm|window\.prompt/);
});
