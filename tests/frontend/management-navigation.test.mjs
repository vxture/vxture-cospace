import {test} from 'node:test';
import assert from 'node:assert/strict';
import {managementPage,managementHref,sceneInformationHref,canOpenSceneWorkspace} from '../../apps/workbench/src/layout/management-contract.ts';
import {sceneLinkFromUrl} from '../../apps/workbench/src/layout/navigation-contract.ts';

test('all four management bookmarks reach two canonical destinations without record scope',()=>{
 assert.equal(managementPage('members'),'settings');
 assert.equal(managementPage('identity'),'account');
 for(const route of ['settings','members'])assert.equal(managementHref(route,'scene A&B'),'/settings?space=scene+A%26B');
 for(const route of ['identity','account'])assert.equal(managementHref(route,'scene A&B'),'/account');
 assert.equal(managementHref('settings'),'/settings');
});
test('scene information preserves selected scene and drops old workflow records',()=>{
 assert.equal(sceneInformationHref('scene A&B'),'/build?space=scene+A%26B&tab=info');
 assert.equal(sceneLinkFromUrl('build','new','/build?space=old&tab=info&job=oldjob'),'/build?space=new&tab=info');
});
test('viewers can read basic information without gaining build or management operations',()=>{
 const viewer=['space.preview','space.query'];
 assert.equal(canOpenSceneWorkspace('build','info',viewer),true);
 assert.equal(canOpenSceneWorkspace('build','flow',viewer),false);
 assert.equal(canOpenSceneWorkspace('build','tasks',viewer),false);
 assert.equal(canOpenSceneWorkspace('build','info',[]),false);
 assert.equal(canOpenSceneWorkspace('association','objects',viewer),false);
 assert.equal(canOpenSceneWorkspace('data','inputs',viewer),false);
 assert.equal(canOpenSceneWorkspace('build','flow',['build.run']),true);
});
