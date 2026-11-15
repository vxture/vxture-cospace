import {test} from 'node:test';
import assert from 'node:assert/strict';
import {assistantAvailable,assistantScope,buildAssistantReport} from '../../apps/workbench/src/layout/assistant-contract.ts';

const base={loading:false,error:'',canBuild:true,canPublish:true,inputs:1,model:false,selected:false,published:false};
test('assistant covers business modules and management but excludes the three browsing areas',()=>{
 for(const route of ['','home','space'])assert.equal(assistantAvailable(route),false);
 for(const route of ['data','build','ontology','association','delivery','services','settings','account','members','identity'])assert.equal(assistantAvailable(route),true);
});
test('task scope changes across account, scene, fixed version and detail changes',()=>{
 const scope=assistantScope('services','/services?space=a&publication=one','user-a');
 for(const [route,url,session] of [['services','/services?space=b&publication=one','user-a'],['services','/services?space=a&publication=two','user-a'],['services','/services?space=a&publication=one','user-b'],['delivery','/delivery?space=a','user-a']])assert.notEqual(assistantScope(route,url,session),scope);
});
test('unreadable or unauthorized facts never generate actionable build suggestions',()=>{
 for(const changes of [{loading:true},{error:'读取失败'},{canBuild:false}])assert.equal(buildAssistantReport({...base,...changes},()=>{}).tasks.length,0);
});
test('build checks follow saved facts and only execute the selected handoff',()=>{
 const cases=[ [{inputs:0},'prepare'],[{},'check'],[{state:'failed'},'model'],[{state:'interrupted'},'model'],[{state:'views_failed'},'model'],[{state:'queued'},'model'],[{state:'running'},'model'],[{state:'succeeded',model:true},'review'],[{state:'succeeded',model:true,selected:true},'publish'] ];
 for(const [changes,expected] of cases){
  const calls=[];const report=buildAssistantReport({...base,...changes},step=>calls.push(step));
  assert.equal(report.status,'ready');assert.equal(report.tasks[0].id,expected);assert.deepEqual(calls,[]);
  assert.ok(report.tasks[0].evidence);report.tasks[0].run();assert.deepEqual(calls,[expected]);
 }
 assert.equal(buildAssistantReport({...base,state:'succeeded',model:true,selected:true,published:true},()=>{}).tasks.length,0);
 assert.equal(buildAssistantReport({...base,state:'succeeded',model:true,selected:true,canPublish:false},()=>{}).tasks.length,0);
});
