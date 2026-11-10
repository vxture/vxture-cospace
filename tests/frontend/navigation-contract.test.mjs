import {test} from 'node:test';
import assert from 'node:assert/strict';
import {moduleLinkFromUrl,recordLinkFromUrl,sceneLinkFromUrl,headerSceneLinkFromUrl} from '../../apps/workbench/src/layout/navigation-contract.ts';
import {moduleNames,moduleScopes} from '../../apps/workbench/src/layout/product-navigation.ts';

test('all module switches preserve only scene context, including shared support filters',()=>{
 const source='/build?space=scene-a&tab=tasks&input=input-a&check=12&batch=batch-a&job=job-a&publication=old&artifact=candidate-a&from=data&ontology_id=rule-a&ontology_version=1&ontology_sha256=abc';
 for(const route of Object.keys(moduleNames))assert.equal(moduleLinkFromUrl(route,source),`/${route}?space=scene-a`);
});

test('scope classification keeps data and ontology independent of scene workflow',()=>{
 assert.deepEqual(Object.keys(moduleScopes).filter(route=>moduleScopes[route]==='support').sort(),['data','ontology']);
 assert.deepEqual(Object.keys(moduleScopes).sort(),Object.keys(moduleNames).sort());
});

test('no scene is invented and an explicit inaccessible scene is not replaced',()=>{
 assert.equal(moduleLinkFromUrl('ontology','/data?job=old'),'/ontology?');
 assert.equal(moduleLinkFromUrl('data','/ontology'),'/data?');
 assert.equal(moduleLinkFromUrl('build','/data?space=unavailable'),'/build?space=unavailable');
});

test('explicit handoffs retain target records and override scene without carrying old records',()=>{
 const source='/data?space=scene-a&input=old&job=old&publication=old';
 assert.equal(recordLinkFromUrl('build',{input:'selected',batch:'batch-a',tab:'flow'},source),'/build?space=scene-a&input=selected&batch=batch-a&tab=flow');
 assert.equal(recordLinkFromUrl('delivery',{space:'scene-b',publication:'fixed-b'},source),'/delivery?space=scene-b&publication=fixed-b');
 assert.equal(recordLinkFromUrl('data',{space:'',tab:'inputs'},source),'/data?space=&tab=inputs');
});

test('URL context remains tab-local, encoded and independent of global last-scene state',()=>{
 assert.equal(moduleLinkFromUrl('build','/data?space=%E5%9C%BA%E6%99%AF+A%26B'),'/build?space=%E5%9C%BA%E6%99%AF+A%26B');
 const a=moduleLinkFromUrl('space','/delivery?space=a&publication=one');
 const b=moduleLinkFromUrl('space','/delivery?space=b&publication=two');
 assert.equal(a,'/space?space=a');assert.equal(b,'/space?space=b');
});


test('scene selection preserves valid capabilities and clears every old record',()=>{
 const source='/build?space=old&tab=tasks&job=old&input=old&check=12&batch=old&publication=old';
 assert.equal(sceneLinkFromUrl('build','next',source),'/build?space=next&tab=tasks');
 assert.equal(sceneLinkFromUrl('association','next',source),'/association?space=next');
 assert.equal(sceneLinkFromUrl('build','',source),'/build?space=&tab=tasks');
 assert.equal(sceneLinkFromUrl('data','next','/data?space=old&tab=lineage&artifact=old'),'/data?space=next&tab=lineage');
});

test('header selection keeps service section but never previous scene records',()=>{
 assert.equal(headerSceneLinkFromUrl('next','/services?section=offline&space=old&publication=old&job=old'),'/services?space=next&section=offline');
 assert.equal(headerSceneLinkFromUrl('next','/build?space=old&tab=tasks&job=old'),'/build?space=next&tab=tasks');
 assert.equal(headerSceneLinkFromUrl('A&B','/space?screen=space&publication=old'),'/space?space=A%26B');
 assert.equal(headerSceneLinkFromUrl('next','/services?section=invalid&artifact=old'),'/services?space=next');
});
