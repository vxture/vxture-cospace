import test from 'node:test';
import assert from 'node:assert/strict';
import {homeSceneEntry} from '../../apps/workbench/src/layout/scene-catalog-contract.ts';
const scene={id:'space-one',name:'one',project_id:'p',state:'no_publication',capabilities:['space.preview','data.manage','build.run']};
test('unpublished home entry opens scoped input management rather than overview drawer',()=>{
 assert.deepEqual(homeSceneEntry(scene),{href:'/data?space=space-one&tab=inputs',label:'数据管理'});
});
test('home entry respects module permissions for builders and viewers',()=>{
 assert.equal(homeSceneEntry({...scene,capabilities:['build.run']}).href,'/build?space=space-one');
 assert.equal(homeSceneEntry({...scene,capabilities:['space.preview']}).href,'/services?section=directory&space=space-one&tab=recipients');
 assert.equal(homeSceneEntry({...scene,capabilities:[]}).href,'/space');
});
test('only explicit active release opens spatial preview',()=>{
 const publication={id:'publication-one',candidate_id:'build-one',preview_url:'',created_at:'2026-11-13T00:00:00Z',lifecycle_state:'active'};
 const published={...scene,publication_id:publication.id,publications:[publication]};
 assert.equal(homeSceneEntry(published).href,'/space?screen=space&preview=1&space=space-one&publication=publication-one');
 assert.equal(homeSceneEntry({...published,publications:[{...publication,lifecycle_state:'paused'}]}).href,'/data?space=space-one&tab=inputs');
});
