import {test} from 'node:test';
import assert from 'node:assert/strict';
import {scenePhase,filterScenes,sceneWorkspaceHref,sceneDestinations,currentRelease,sceneEntryHref,publicationLabel,publicationAvailable} from '../../apps/workbench/src/layout/scene-catalog-contract.ts';

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
 assert.deepEqual(items.map(s=>[s.key,s.enabled]),[['data',true],['build',false],['delivery',true],['settings',true]]);
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
 assert.equal(sceneWorkspaceHref('scene A&B'),'/space?space=scene+A%26B');
});


test('scene entry opens only the explicit active current publication and preserves legacy details links',()=>{
 const active={id:'release &1',lifecycle_state:'active',display_code:'S301178-B01-P02'};
 const scene={id:'scene A&B',publication_id:active.id,publications:[{id:'newer',lifecycle_state:'active'},active]};
 assert.equal(currentRelease(scene),active);
 const url=new URL(sceneEntryHref(scene),'https://example.test');
 assert.equal(url.searchParams.get('publication'),active.id);
 assert.equal(url.searchParams.get('space'),scene.id);
 assert.equal(url.searchParams.get('screen'),'space');
 assert.equal(publicationLabel(active),'S301178-B01-P02');
 assert.equal(publicationLabel({id:'old',version_code:'P01'}),'P01');
 assert.equal(publicationLabel({id:'old'}),'old');
 for(const lifecycle_state of ['paused','retired','unknown',undefined]){
  const blocked={...scene,publications:[{...active,lifecycle_state},{id:'other',lifecycle_state:'active'}]};
  assert.equal(currentRelease(blocked),undefined);
  assert.equal(sceneEntryHref(blocked),sceneWorkspaceHref(scene.id));
  assert.equal(publicationAvailable(blocked.publications[0]),false);
 }
 assert.equal(sceneEntryHref({...scene,publication_id:'missing'}),sceneWorkspaceHref(scene.id));
 assert.equal(sceneEntryHref({id:'empty'}),'/space?space=empty');
 const info=sceneDestinations({id:scene.id,capabilities:['space.preview']}).find(d=>d.key==='settings');
 assert.equal(info.enabled,true);
 assert.equal(info.label,'基本信息');
 assert.equal(info.href,'/build?space=scene+A%26B&tab=info');
});
