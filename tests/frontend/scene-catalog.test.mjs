import {test} from 'node:test';
import assert from 'node:assert/strict';
import {scenePhase,filterScenes,sceneWorkspaceHref,sceneDestinations} from '../../apps/workbench/src/layout/scene-catalog-contract.ts';

test('catalog reflects actual publication lifecycle without inventing published versions',()=>{
 assert.equal(scenePhase({state:'no_publication'}),'building');
 assert.equal(scenePhase({state:'preview_published',publication_id:'fixed'}),'published');
 assert.equal(scenePhase({state:'distribution_paused',publications:[{lifecycle_state:'paused'}]}),'paused');
 assert.equal(scenePhase({state:'distribution_paused',publications:[{lifecycle_state:'retired'}]}),'archived');
 assert.equal(scenePhase({state:'preview_published'}),'unavailable');
 assert.equal(scenePhase({state:'unrecognized'}),'unavailable');
});

test('newest activity sorts across phases, with invalid or missing dates last',()=>{
 const spaces=[{id:'old',name:'A',state:'preview_published',publication_id:'old',created_at:'2026-01-01'},
  {id:'new',name:'Z',state:'no_publication',updated_at:'2026-11-09T10:00:00Z'},
  {id:'release',name:'B',state:'preview_published',publications:[{created_at:'2026-11-08T10:00:00Z'},{created_at:'invalid'}]},
  {id:'missing',name:'C',created_at:'invalid'}];
 assert.deepEqual(filterScenes(spaces,'','all','time').map(s=>s.id),['new','release','old','missing']);
 assert.deepEqual(filterScenes(spaces,'','building','time').map(s=>s.id),['new']);
 assert.deepEqual(spaces.map(s=>s.id),['old','new','release','missing']);
});

test('scene operation destinations retain disabled entries and explicit scene scope',()=>{
 const items=sceneDestinations({id:'scene A&B',capabilities:['space.preview','data.manage']});
 assert.deepEqual(items.map(s=>[s.key,s.enabled]),[['data',true],['build',false],['delivery',true],['settings',false]]);
 assert.equal(items[0].href,'/data?space=scene+A%26B');
 assert.ok(sceneDestinations({id:'none'}).every(s=>!s.enabled));
});

test('search and state filtering preserve source total and sort by progress',()=>{
 const spaces=[{id:'b',name:'B',state:'no_publication',project_name:'设备园区'},
  {id:'a',name:'A',state:'preview_published',publication_id:'fixed',address:'上海'},
  {id:'c',name:'C',state:'distribution_paused'}];
 assert.deepEqual(filterScenes(spaces,'','all','phase').map(s=>s.id),['a','b','c']);
 assert.deepEqual(filterScenes(spaces,'  设备  ','all','phase').map(s=>s.id),['b']);
 assert.deepEqual(filterScenes(spaces,'上海','published','phase').map(s=>s.id),['a']);
 assert.equal(filterScenes(spaces,'上海','building','phase').length,0);
 assert.deepEqual(spaces.map(s=>s.id),['b','a','c']);
 assert.equal(sceneWorkspaceHref('scene A&B'),'/build?space=scene+A%26B&tab=info');
});
