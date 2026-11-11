import {test} from 'node:test';
import assert from 'node:assert/strict';
import {associationSource,keepsAssociationDrafts} from '../../apps/workbench/src/layout/association-context.ts';

const rows=[
 {id:'base',space_id:'a',state:'succeeded',created_at:'2026-11-11T00:00:00Z'},
 {id:'failed',space_id:'a',state:'failed',created_at:'2026-11-11T00:00:00Z'},
 {id:'foreign',space_id:'b',state:'succeeded',created_at:'2026-11-11T00:00:00Z'},
];
test('explicit missing, failed or foreign sources never fall back to the current selection',()=>{
 for(const identity of ['missing','failed','foreign'])assert.equal(associationSource(rows,'a',identity,'base').current,undefined);
 assert.equal(associationSource(rows,'a','','base').current.id,'base');
 assert.equal(associationSource(rows,'a','',null).current,undefined);
 assert.deepEqual(associationSource(rows,'a','','base').available.map(j=>j.id),['base']);
});
test('only association function-page changes preserve mounted drafts',()=>{
 const current='/association?space=a&job=base&tab=objects';
 for(const tab of ['overview','objects','relations','business','ifc','info'])assert.equal(keepsAssociationDrafts(current,`/association?job=base&tab=${tab}&space=a`),true);
 for(const next of ['/association?space=a&job=new&tab=relations','/association?space=b&job=base&tab=relations','/build?space=a&job=base&tab=flow','/association?space=a&job=base&tab=unknown','/association?space=a&job=base&tab=relations&from=elsewhere'])assert.equal(keepsAssociationDrafts(current,next),false);
 assert.equal(keepsAssociationDrafts('/association?space=a&tab=objects','/association?space=a&tab=info'),false);
});
