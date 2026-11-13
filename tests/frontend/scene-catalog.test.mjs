import {test} from 'node:test';
import assert from 'node:assert/strict';
import {hasPreviewModelSummary} from '../../apps/workbench/src/layout/preview-model-contract.ts';
import {sceneBuildMode,sceneViewSummary} from '../../apps/workbench/src/layout/scene-overview-contract.ts';

test('overview uses declared build mode and never invents independent view completion',()=>{
 assert.equal(sceneBuildMode({input_binding:{format:'ply_pointcloud'}}),'已有点云 · 整理与表达派生');
 assert.equal(sceneBuildMode({view_parent_id:'parent',input_binding:{format:'ply_pointcloud'}}),'沿用基准模型 · 视图派生');
 assert.equal(sceneBuildMode({mode:'unknown'}),'构建模式未记录');
 assert.equal(sceneViewSummary(null,'human'),'派生记录暂不可读');
 assert.equal(sceneViewSummary({legacy:true,views:{}},'human'),'历史构建未记录独立派生状态');
 const stages={views:{human:{state:'succeeded'},agent:{state:'failed'}}};
 assert.equal(sceneViewSummary(stages,'human'),'已派生');
 assert.equal(sceneViewSummary(stages,'agent'),'派生失败');
 assert.equal(sceneViewSummary({views:{}},'agent'),'尚未派生');
});
import {scenePhase,filterScenes,sceneWorkspaceHref,sceneDestinations,currentRelease,sceneEntryHref,sceneEntryLabel,publicationLabel,publicationAvailable} from '../../apps/workbench/src/layout/scene-catalog-contract.ts';

test('catalog reflects actual publication lifecycle without inventing published versions',()=>{
 assert.equal(scenePhase({state:'no_publication'}),'building');
 assert.equal(scenePhase({state:'preview_published',publication_id:'fixed'}),'published');
 assert.equal(scenePhase({state:'distribution_paused',publications:[{lifecycle_state:'paused'}]}),'paused');
 assert.equal(scenePhase({state:'distribution_paused',publications:[{lifecycle_state:'retired'}]}),'archived');
 assert.equal(scenePhase({state:'preview_published'}),'unavailable');
 assert.equal(scenePhase({state:'unrecognized'}),'unavailable');
});

test('scene handoff targets reject incomplete historical model summaries before rendering',()=>{
 const model={construction:{model_points:0},human_view:{path:'human.ply'},agent_view:{path:'agent.json',surface_cells:0},
  members:{'spatial.npz':{bytes:20},'human.ply':{bytes:40},'agent.json':{bytes:10}}};
 assert.equal(hasPreviewModelSummary(model),true);
 for(const incomplete of [null,{}, {...model,construction:undefined}, {...model,construction:{model_points:'100'}},
  {...model,agent_view:{path:'agent.json'}},{...model,human_view:{path:'missing.ply'}},
  {...model,members:undefined},{...model,construction:{model_points:-1}}]){
  assert.equal(hasPreviewModelSummary(incomplete),false);
 }
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
 assert.deepEqual(items.map(s=>[s.key,s.enabled]),[['services',true],['build',false],['association',false],['delivery',true],['data',true]]);
 assert.equal(items.find(item=>item.key==='data').href,'/data?space=scene+A%26B');
 assert.equal(new URL(items[0].href,'https://example.test').pathname,'/services');
 assert.ok(sceneDestinations({id:'none'}).every(s=>!s.enabled));
});

test('scene handoffs use only the selected scene and honor each operation permission',()=>{
 const scene={id:'scene A&B',capabilities:['space.preview','data.manage','build.run','association.edit']};
 const destinations=sceneDestinations(scene);
 for(const item of destinations){
  const url=new URL(item.href,'https://example.test');
  assert.equal(url.searchParams.get('space'),scene.id);
  assert.equal(url.searchParams.has('publication'),false);
  assert.equal(url.searchParams.has('job'),false);
  assert.equal(item.enabled,true);
 }
 assert.equal(destinations.find(item=>item.key==='association').href,'/association?space=scene+A%26B');
 assert.equal(sceneDestinations({...scene,capabilities:['space.preview']}).find(item=>item.key==='association').enabled,false);
});

test('catalog status and entry agree with the explicitly current release, independent of history order',()=>{
 const active={id:'current',lifecycle_state:'active'};
 const scene={id:'scene',state:'preview_published',publication_id:active.id,
  publications:[{id:'old',lifecycle_state:'retired'},active]};
 assert.equal(scenePhase(scene),'published');
 assert.equal(sceneEntryLabel(scene),'空间预览');
 for(const lifecycle_state of ['paused','retired','unknown']){
  const blocked={...scene,publications:[{id:'other',lifecycle_state:'active'},{...active,lifecycle_state}]};
  assert.equal(scenePhase(blocked),lifecycle_state==='paused'?'paused':lifecycle_state==='retired'?'archived':'unavailable');
  assert.equal(sceneEntryLabel(blocked),'场景概览');
  assert.equal(sceneEntryHref(blocked),sceneWorkspaceHref(scene.id));
 }
 assert.equal(scenePhase({...scene,publications:[]}), 'unavailable');
 assert.equal(sceneEntryLabel({id:'empty',state:'no_publication'}),'场景概览');
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
 assert.equal(sceneDestinations({id:scene.id,capabilities:['space.preview']}).some(d=>d.key==='settings'),false);
});


test('scene services menu pins current release and routes unpublished scenes to recipients',()=>{
 const scene={id:'space-123',publication_id:'fixed-1',capabilities:['space.preview']};
 const url=new URL(sceneDestinations(scene)[0].href,'https://example.test');
 assert.equal(url.pathname,'/services');
 assert.equal(url.searchParams.get('space'),scene.id);
 assert.equal(url.searchParams.get('publication'),'fixed-1');
 assert.equal(url.searchParams.get('tab'),'overview');
 const empty=new URL(sceneDestinations({...scene,publication_id:undefined})[0].href,'https://example.test');
 assert.equal(empty.searchParams.get('tab'),'recipients');
 assert.equal(empty.searchParams.has('publication'),false);
});
