import test from 'node:test';
import assert from 'node:assert/strict';
import {homeMonitorStatus} from '../../apps/workbench/src/layout/home-monitor-status.ts';

const normal={failed:0,rejected:0,partial:false,configuration:'configured'};
test('complete configured monitoring without errors is normal blue',()=>{
 assert.deepEqual(homeMonitorStatus([normal],false,0),{label:'正常',tone:'brand'});
});
test('service errors and invalid configuration take precedence over coverage gaps',()=>{
 for(const row of [{...normal,failed:2,partial:true},{...normal,configuration:'unavailable'}]){
  assert.deepEqual(homeMonitorStatus([row],false,1),{label:'异常',tone:'danger'});
 }
});
test('policy rejection has warning severity rather than service failure',()=>{
 assert.deepEqual(homeMonitorStatus([{...normal,rejected:1}],false,0),{label:'请求受阻',tone:'warning'});
});
test('missing or incomplete monitoring never asserts normal',()=>{
 for(const [rows,loading,errors] of [[[],false,0],[[normal],true,0],[[normal],false,1],[[{...normal,partial:true}],false,0]]){
  assert.equal(homeMonitorStatus(rows,loading,errors).tone,'neutral');
 }
});
test('unconfigured integration remains neutral rather than an error',()=>{
 assert.deepEqual(homeMonitorStatus([{...normal,configuration:'not_configured'}],false,0),{label:'待配置',tone:'neutral'});
});
