import test from 'node:test';
import assert from 'node:assert/strict';
import {compareDefinitions} from '../../apps/workbench/src/layout/ontology-diff.ts';
const base={ontology_id:'rule',version:'1.0.0',title:'Rule',types:{room:{title:'Room',properties:{name:{required:false,min_length:0,max_length:20}}}}};
test('version alone and object property order do not create content changes',()=>{
 assert.equal(compareDefinitions(base,{...base,version:'2.0.0'}).total,0);
 assert.equal(compareDefinitions({ontology_id:'rule',a:{x:1,y:2}},{a:{y:2,x:1},ontology_id:'rule'}).total,0);
});
test('constraint and description differences remain distinct and directional',()=>{
 const after=structuredClone(base);after.title='Changed';after.types.room.properties.name.required=true;
 const diff=compareDefinitions(base,after);
 assert.equal(diff.total,2);assert.equal(diff.items.find(v=>v.path==='/title').review,false);
 assert.deepEqual(diff.items.find(v=>v.path.endsWith('/required')),{path:'/types/room/properties/name/required',kind:'changed',before:'false',after:'true',review:true});
});
test('deletion additions relation changes escaped IDs and bounded display',()=>{
 const diff=compareDefinitions({ontology_id:'r',types:{'a/b':{x:1}}},{ontology_id:'r',types:{'a~b':{x:2}},relations:{connected:{symmetric:true}}});
 assert.ok(diff.items.some(v=>v.path.includes('a~1b')&&v.kind==='removed'));
 assert.ok(diff.items.some(v=>v.path.includes('a~0b')&&v.kind==='added'));
 assert.ok(diff.items.some(v=>v.path==='/relations/connected/symmetric'&&v.review));
 const large=compareDefinitions({ontology_id:'r'},{ontology_id:'r',types:Object.fromEntries(Array.from({length:250},(_,i)=>['t'+i,i]))});
 assert.equal(large.total,250);assert.equal(large.items.length,200);assert.equal(large.truncated,true);
 assert.throws(()=>compareDefinitions(base,{ontology_id:'other'}));
});
