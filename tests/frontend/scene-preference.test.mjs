import {test} from 'node:test';
import assert from 'node:assert/strict';
import {preferredScene,sceneContextHref,scenePreferenceKey} from '../../apps/workbench/src/layout/scene-preference.ts';

test('explicit links and deliberate clearing take precedence over remembered scene',()=>{
 assert.equal(preferredScene('linked','remembered'),'linked');
 assert.equal(preferredScene('','remembered'),'');
 assert.equal(preferredScene(null,'remembered'),'remembered');
});
test('scene preference is isolated between account, organization and workspace',()=>{
 const keys=[['org-a','ws-a','user-a'],['org-a','ws-a','user-b'],['org-b','ws-a','user-a'],['org-a','ws-b','user-a']].map(scope=>scenePreferenceKey(JSON.stringify(scope)));
 assert.equal(new Set(keys).size,4);
});
test('global context retains module queries and explicit scene, while catalog remains open',()=>{
 assert.equal(sceneContextHref('/services?section=offline','A&B'),'/services?section=offline&space=A%26B');
 assert.equal(sceneContextHref('/build?tab=tasks','saved'),'/build?tab=tasks&space=saved');
 assert.equal(sceneContextHref('/build?space=linked','saved'),'/build?space=linked');
 assert.equal(sceneContextHref('/space','saved'),'/space');
 assert.equal(sceneContextHref('/','saved'),'/');
 assert.equal(sceneContextHref('/data?space=','saved'),'/data?space=');
});
