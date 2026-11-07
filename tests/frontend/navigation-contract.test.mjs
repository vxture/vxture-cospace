import {test} from 'node:test';
import assert from 'node:assert/strict';
import {moduleLinkFromHash,recordLinkFromHash,sceneLinkFromHash} from '../../apps/workbench/src/layout/navigation-contract.ts';
import {moduleNames,moduleScopes} from '../../apps/workbench/src/layout/product-navigation.ts';

test('all module switches preserve only scene context, including shared support filters',()=>{
 const source='#build?space=scene-a&tab=tasks&input=input-a&check=12&batch=batch-a&job=job-a&publication=old&artifact=candidate-a&from=data&ontology_id=rule-a&ontology_version=1&ontology_sha256=abc';
 for(const route of Object.keys(moduleNames))assert.equal(moduleLinkFromHash(route,source),`#${route}?space=scene-a`);
});

test('scope classification keeps data and ontology independent of scene workflow',()=>{
 assert.deepEqual(Object.keys(moduleScopes).filter(route=>moduleScopes[route]==='support').sort(),['data','ontology']);
 assert.deepEqual(Object.keys(moduleScopes).sort(),Object.keys(moduleNames).sort());
});

test('no scene is invented and an explicit inaccessible scene is not replaced',()=>{
 assert.equal(moduleLinkFromHash('ontology','#data?job=old'),'#ontology?');
 assert.equal(moduleLinkFromHash('data','#ontology'),'#data?');
 assert.equal(moduleLinkFromHash('build','#data?space=unavailable'),'#build?space=unavailable');
});

test('explicit handoffs retain target records and override scene without carrying old records',()=>{
 const source='#data?space=scene-a&input=old&job=old&publication=old';
 assert.equal(recordLinkFromHash('build',{input:'selected',batch:'batch-a',tab:'flow'},source),'#build?space=scene-a&input=selected&batch=batch-a&tab=flow');
 assert.equal(recordLinkFromHash('delivery',{space:'scene-b',publication:'fixed-b'},source),'#delivery?space=scene-b&publication=fixed-b');
 assert.equal(recordLinkFromHash('data',{space:'',tab:'inputs'},source),'#data?space=&tab=inputs');
});

test('URL context remains tab-local, encoded and independent of global last-scene state',()=>{
 assert.equal(moduleLinkFromHash('build','#data?space=%E5%9C%BA%E6%99%AF+A%26B'),'#build?space=%E5%9C%BA%E6%99%AF+A%26B');
 const a=moduleLinkFromHash('space','#delivery?space=a&publication=one');
 const b=moduleLinkFromHash('space','#delivery?space=b&publication=two');
 assert.equal(a,'#space?space=a');assert.equal(b,'#space?space=b');
});


test('scene selection preserves valid capabilities and clears every old record',()=>{
 const source='#build?space=old&tab=tasks&job=old&input=old&check=12&batch=old&publication=old';
 assert.equal(sceneLinkFromHash('build','next',source),'#build?space=next&tab=tasks');
 assert.equal(sceneLinkFromHash('association','next',source),'#association?space=next');
 assert.equal(sceneLinkFromHash('build','',source),'#build?space=&tab=tasks');
 assert.equal(sceneLinkFromHash('data','next','#data?space=old&tab=lineage&artifact=old'),'#data?space=next&tab=lineage');
});
