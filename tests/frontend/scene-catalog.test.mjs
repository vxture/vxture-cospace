import {test} from 'node:test';
import assert from 'node:assert/strict';
import {scenePhase,filterScenes,sceneWorkspaceHref} from '../../apps/workbench/src/layout/scene-catalog-contract.ts';

test('catalog reflects actual publication lifecycle without inventing published versions',()=>{
 assert.equal(scenePhase({state:'no_publication'}),'building');
 assert.equal(scenePhase({state:'preview_published',publication_id:'fixed'}),'published');
 assert.equal(scenePhase({state:'distribution_paused',publications:[{lifecycle_state:'paused'}]}),'paused');
 assert.equal(scenePhase({state:'distribution_paused',publications:[{lifecycle_state:'retired'}]}),'archived');
 assert.equal(scenePhase({state:'preview_published'}),'unavailable');
 assert.equal(scenePhase({state:'unrecognized'}),'unavailable');
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
 assert.equal(sceneWorkspaceHref('scene A&B'),'/space?space=scene+A%26B');
});
