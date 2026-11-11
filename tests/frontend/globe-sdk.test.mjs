import test from 'node:test';
import assert from 'node:assert/strict';
import {bindingKey,validateScenes,validateLayers,parseEmbedCommand,trustedParent,GLOBE_PROTOCOL} from '../../packages/globe-sdk/src/contract.ts';
const binding={spaceId:'s1',publicationId:'p1'};
const scenes=[{...binding,name:'A',position:[120,30,5]}];
test('scene and layer bindings preserve exact publication identity',()=>{
 assert.notEqual(bindingKey(binding),bindingKey({...binding,publicationId:'p2'}));
 validateScenes(scenes);
 const layer={id:'robot-a',binding,features:[{id:'track',geometry:{type:'line',positions:[[120,30],[121,31]]}}]};
 validateLayers([layer,{...layer,id:'robot-b'}],scenes);
 assert.throws(()=>validateLayers([{...layer,binding:{...binding,publicationId:'p2'}}],scenes));
 assert.throws(()=>validateLayers([layer,layer],scenes));
 assert.throws(()=>validateScenes([...scenes,...scenes]));
 assert.throws(()=>validateScenes([{...scenes[0],position:[181,30]}]));
 assert.throws(()=>validateLayers([{...layer,features:[{id:'x',geometry:{type:'model',url:'https://bad'}}]}],scenes));
 assert.throws(()=>validateLayers([{...layer,features:[{id:'x',geometry:{type:'line',positions:Array(50001).fill([120,30])}}]}],scenes));
 validateLayers([{...layer,features:[{id:'flight',heightMode:'absolute',geometry:{type:'line',positions:[[120,30,50],[120,30,60]]}}]}],scenes);
 assert.throws(()=>validateLayers([{...layer,features:[{id:'flight',heightMode:'sea-level',geometry:{type:'point',position:[120,30,50]}}]}],scenes));
});
test('embed accepts camera commands only, rejecting credentials, URLs, coordinates and protocol drift',()=>{
 const message={protocol:GLOBE_PROTOCOL,requestId:'one',command:{type:'focus',binding}};
 assert.deepEqual(parseEmbedCommand(message),message);
 for(const value of [{...message,token:'secret'},{...message,protocol:'vxture.globe/1'},{...message,command:{type:'focus',binding:{...binding,url:'https://bad'}}},{...message,command:{type:'focus',position:[120,30]}},{...message,command:{type:'reset',url:'https://bad'}},{...message,command:{type:'setLayers'}},{...message,requestId:''},null])assert.equal(parseEmbedCommand(value),null);
});
test('matching origin alone never authorizes a different frame',()=>{
 const parent={};
 assert.equal(trustedParent({origin:'https://agent.example',source:parent},parent,'https://agent.example'),true);
 assert.equal(trustedParent({origin:'https://agent.example',source:{}},parent,'https://agent.example'),false);
 assert.equal(trustedParent({origin:'https://evil.example',source:parent},parent,'https://agent.example'),false);
});
