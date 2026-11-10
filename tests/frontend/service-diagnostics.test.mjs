import {test} from 'node:test';
import assert from 'node:assert/strict';
import {diagnosticGuidance,lifecycleLabels} from '../../apps/workbench/src/layout/service-diagnostics-contract.ts';

test('freshness refusal is distinct from historic evidence and directs evidence review',()=>{
 assert.equal(diagnosticGuidance('observation_time_unverified').action,'evidence');
 assert.match(diagnosticGuidance('observation_time_unverified').advice,/实时消费已被拒绝/);
 assert.match(diagnosticGuidance('historical_result').advice,/不表示实时可用/);
});
test('lifecycle failures lead to publishing while binding failures lead to integration',()=>{
 for(const key of ['publication_retired','publication_distribution_paused','consumer_publication_not_found'])assert.equal(diagnosticGuidance(key).action,'publishing');
 for(const key of ['consumer_version_mismatch','consumer_frame_mismatch'])assert.equal(diagnosticGuidance(key).action,'integration');
 assert.equal(lifecycleLabels.active,'允许分发');
 assert.equal(lifecycleLabels.unavailable,'状态待核对');
});
test('unknown response codes never imply successful consumption',()=>{
 const value=diagnosticGuidance('future_status');
 assert.equal(value.label,'未分类结果');
 assert.match(value.advice,/不根据未知结果自动继续消费/);
});
