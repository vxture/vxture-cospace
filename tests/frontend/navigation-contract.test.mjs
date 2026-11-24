import './data-catalog.test.mjs';
import './data-sharing.test.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {canonicalModuleHref,moduleLinkFromUrl,recordLinkFromUrl,sceneLinkFromUrl,headerSceneLinkFromUrl} from '../../apps/workbench/src/layout/navigation-contract.ts';
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
 for(const tab of ['overview','access','offline','manage'])assert.equal(headerSceneLinkFromUrl('next',`/delivery?space=old&tab=${tab}&publication=old&job=old`),`/delivery?space=next&tab=${tab}`);
 assert.equal(headerSceneLinkFromUrl('next','/services?section=offline&space=old&publication=old&job=old'),'/services?space=next&section=offline');
 assert.equal(headerSceneLinkFromUrl('next','/build?space=old&tab=tasks&job=old'),'/build?space=next&tab=tasks');
 assert.equal(headerSceneLinkFromUrl('A&B','/space?screen=space&publication=old'),'/space?space=A%26B');
 assert.equal(headerSceneLinkFromUrl('next','/services?section=invalid&artifact=old'),'/services?space=next');
});


test('data bookmarks are unchanged by the removed header scene picker',()=>{
 assert.equal(headerSceneLinkFromUrl('next','/data?space=old&tab=info&input=old&publication=old'),'/data?space=old&tab=info&input=old&publication=old');
});

test('catalog scene switching preserves the catalog route rather than entering legacy preview',()=>{
 assert.equal(headerSceneLinkFromUrl('next','/space'),'/space');
 assert.equal(headerSceneLinkFromUrl('next','/space?filter=ready'),'/space?filter=ready');
});

test('spatial reference bookmarks migrate with fixed model context and scene switches clear old models',()=>{
 assert.equal(canonicalModuleHref('/association?space=scene+A%26B&tab=registration&job=model-fixed&example=equipment'),'/registration?space=scene+A%26B&job=model-fixed');
 assert.equal(canonicalModuleHref('/association?tab=registration&space='),'/registration?space=');
 assert.equal(canonicalModuleHref('/association?space=a&tab=objects&job=fixed'),'/association?space=a&tab=objects&job=fixed');
 assert.equal(canonicalModuleHref('/registration?space=a&job=fixed'),'/registration?space=a&job=fixed');
 assert.equal(headerSceneLinkFromUrl('next','/registration?space=old&job=model-old&publication=old'),'/registration?space=next');
 assert.equal(headerSceneLinkFromUrl('next','/registration?space=old&job=model-old&tab=info'),'/registration?space=next&tab=info');
 assert.equal(recordLinkFromUrl('registration',{space:'a',job:'fixed'},'/association?space=a&example=equipment&tab=overview'),'/registration?space=a&job=fixed');
});
