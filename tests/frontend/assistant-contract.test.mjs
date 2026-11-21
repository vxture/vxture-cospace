import {test} from 'node:test';
import assert from 'node:assert/strict';
import {assistantAvailable,assistantScope,buildAssistantReport} from '../../apps/workbench/src/layout/assistant-contract.ts';

const base={loading:false,error:'',canBuild:true,canRegister:true,inputs:1,model:false,selected:false};
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
 const cases=[ [{inputs:0},'prepare'],[{},'check'],[{state:'failed'},'model'],[{state:'interrupted'},'model'],[{state:'views_failed'},'model'],[{state:'queued'},'model'],[{state:'running'},'model'],[{state:'succeeded',model:true},'review'],[{state:'succeeded',model:true,selected:true},'registration'] ];
 for(const [changes,expected] of cases){
  const calls=[];const report=buildAssistantReport({...base,...changes},step=>calls.push(step));
  assert.equal(report.status,'ready');assert.equal(report.tasks[0].id,expected);assert.deepEqual(calls,[]);
  assert.ok(report.tasks[0].evidence);report.tasks[0].run();assert.deepEqual(calls,[expected]);
 }
 assert.equal(buildAssistantReport({...base,state:'succeeded',model:true,selected:true,canRegister:false},()=>{}).tasks.length,0);
});

test('conversation retrieves current suggestions without calling business operations',async()=>{
 const {matchAssistantTasks}=await import('../../apps/workbench/src/layout/assistant-contract.ts');
 let calls=0;
 const report={title:'设备检查',status:'ready',tasks:[{id:'dog',title:'补全设备资料',evidence:'机器狗02 厂家尚未补全',label:'编辑资料',run:()=>calls++},{id:'drone',title:'关联作业场景',evidence:'无人机01 尚未关联场景',label:'配置关联',run:()=>calls++}]};
 assert.deepEqual(matchAssistantTasks('无人机01',report).map(t=>t.id),['drone']);
 assert.deepEqual(matchAssistantTasks('推荐操作',report).map(t=>t.id),['dog','drone']);
 assert.deepEqual(matchAssistantTasks('删除所有账户',report),[]);
 assert.deepEqual(matchAssistantTasks('   ',report),[]);
 for(const status of ['loading','error'])assert.deepEqual(matchAssistantTasks('无人机01',{...report,status}),[]);
 assert.equal(calls,0);
});

test('authorization modes remain bounded preferences and task signatures expire on changed facts',async()=>{
 const {assistantConfirmationModes,assistantTaskSignature}=await import('../../apps/workbench/src/layout/assistant-contract.ts');
 assert.deepEqual(assistantConfirmationModes.map(m=>m.label),['逐项确认','常规授权','充分授权']);
 assert.equal(new Set(assistantConfirmationModes.map(m=>m.icon)).size,3);
 const task={id:'one',title:'关联场景',evidence:'设备尚未关联',label:'进入表单',run:()=>{}};
 assert.equal(assistantTaskSignature(task),assistantTaskSignature({...task,run:()=>null}));
 for(const change of [{id:'two'},{evidence:'设备已关联'},{label:'其他操作'}])assert.notEqual(assistantTaskSignature(task),assistantTaskSignature({...task,...change}));
});
