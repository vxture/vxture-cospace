import {test} from 'node:test';
import assert from 'node:assert/strict';
import {managementPage,managementHref,sceneInformationHref,canOpenSceneWorkspace} from '../../apps/workbench/src/layout/management-contract.ts';
import {sceneLinkFromUrl} from '../../apps/workbench/src/layout/navigation-contract.ts';

test('all four management bookmarks reach two canonical destinations without record scope',()=>{
 assert.equal(managementPage('members'),'settings');
 assert.equal(managementPage('identity'),'account');
 assert.equal(managementHref('settings','scene A&B'),'/settings?space=scene+A%26B');
 assert.equal(managementHref('members','scene A&B'),'/settings?space=scene+A%26B&section=members');
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
 assert.equal(canOpenSceneWorkspace('registration','',viewer),false);
 assert.equal(canOpenSceneWorkspace('registration','',['association.edit']),true);
 assert.equal(canOpenSceneWorkspace('data','inputs',viewer),false);
 assert.equal(canOpenSceneWorkspace('build','flow',['build.run']),true);
});


test('settings sections keep scene scope and reject unknown destinations',async()=>{
 const {managementSection,managementSections,productRoleDefinitions}=await import('../../apps/workbench/src/layout/management-contract.ts');
 for(const section of Object.keys(managementSections)){
  const href=managementHref('settings','scene A&B',section),url=new URL(href,'https://example.test');
  assert.equal(url.searchParams.get('space'),section==='ontology-groups'?null:'scene A&B');
  assert.equal(managementSection(url.searchParams.get('section')),section);
 }
 assert.equal(managementSection('platform-billing'),'overview');
 assert.equal(managementHref('account','scene','permissions'),'/account');
 assert.equal(productRoleDefinitions.length,4);
 assert.equal(productRoleDefinitions.find(r=>r.role==='工程师').members,'无人员授权权限');
 assert.equal(productRoleDefinitions.find(r=>r.role==='管理者').members,'对应管理范围内授权');
});


test('ontology group configuration has a settings destination independent of scenes',()=>{
 assert.equal(managementHref('settings','old-scene','ontology-groups'),'/settings?section=ontology-groups');
});
