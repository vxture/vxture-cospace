import {test} from 'node:test';
import assert from 'node:assert/strict';
import {associationExamples,legacyExampleHref} from '../../apps/workbench/src/layout/association-examples.ts';
import {headerSceneLinkFromUrl,recordLinkFromUrl} from '../../apps/workbench/src/layout/navigation-contract.ts';

test('all three retired bookmarks select the template without treating it as a scene or carrying records',()=>{
 for(const item of associationExamples){
  const href=legacyExampleHref(`/space?screen=space&preview=1&space=${item.id}&job=foreign`);
  const params=new URL(href,'https://test.invalid').searchParams;
  assert.equal(params.get('space'),'');assert.equal(params.get('example'),item.id);
  assert.equal(params.get('tab'),'objects');assert.equal(params.has('job'),false);
  const selected=headerSceneLinkFromUrl('authorized-space',href);
  assert.equal(new URL(selected,'https://test.invalid').searchParams.get('example'),item.id);
  assert.equal(new URL(selected,'https://test.invalid').searchParams.get('space'),'authorized-space');
  assert.equal(new URL(recordLinkFromUrl('association',{job:'fixed-model',tab:'relations'},selected),'https://test.invalid').searchParams.get('example'),item.id);
 }
 for(const href of ['/space?screen=space&space=equipment&publication=fixed','/space?space=equipment','/space?screen=space&space=real-space','/services?screen=space&space=pump'])assert.equal(legacyExampleHref(href),null);
});

test('templates preserve nine distinct devices without asserting any model location',()=>{
 const objects=associationExamples.flatMap(e=>e.objects);
 assert.equal(objects.length,9);assert.equal(new Set(objects.map(o=>o.id)).size,9);
 assert.deepEqual(objects.filter(o=>o.type==='pump').map(o=>o.name),['泵组 P-01','泵组 P-02']);
 for(const obj of objects)for(const field of ['point_index','anchor_m','position','frame_id'])assert.equal(field in obj,false);
});
