import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildTiming,buildTimingDefaults,timingDuration} from '../../apps/workbench/src/layout/build-timing.ts';

const at=minute=>new Date(Date.UTC(2026,10,22,0,minute)).toISOString();
const complete={sceneCreatedAt:at(0),input:{registered_at:at(20)},job:{state:'succeeded',created_at:at(24),started_at:at(25),finished_at:at(35)},reviewedAt:at(40),selected:true,now:at(60)};
const ordered=result=>{
 assert.equal(result.stages.length,4);
 for(const [i,s] of result.stages.entries()){
  assert.ok(Number.isFinite(Date.parse(s.start))&&Number.isFinite(Date.parse(s.end)));
  assert.ok(Date.parse(s.end)>=Date.parse(s.start));
  assert.ok(Number.isFinite(s.seconds)&&s.seconds>=0);
  if(i)assert.equal(s.start,result.stages[i-1].end);
 }
 assert.equal(result.totalSeconds,result.elapsedSeconds+result.remainingSeconds);
};

test('new scene starts at creation, accrues without inputs, and forecasts all four steps',()=>{
 assert.deepEqual(buildTimingDefaults,[20,5,10,5]);
 const value=buildTiming({sceneCreatedAt:at(0),now:at(5)});
 ordered(value);assert.equal(value.start,at(0));assert.equal(value.startSource,'recorded');
 assert.equal(value.elapsedSeconds,300);assert.equal(value.remainingSeconds,35*60);assert.equal(value.totalSeconds,40*60);
 assert.deepEqual(value.stages.map(s=>s.state),['current','pending','pending','pending']);
 assert.equal(value.complete,false);
 assert.equal(value.elapsedEstimated,false);
});

test('actual dates replace demo estimates and preserve sub-minute and zero durations',()=>{
 const value=buildTiming({...complete,job:{...complete.job,demo_timeline:{stages:Array(4).fill({start:at(50),end:at(55),estimated:true})}}});
 ordered(value);assert.equal(value.estimated,false);assert.equal(value.elapsedSeconds,40*60);assert.equal(value.remainingSeconds,0);
 assert.equal(value.stages[2].seconds,600);assert.equal(value.stages[2].start,at(25));
 const zero=buildTiming({...complete,input:{registered_at:at(0)},job:{...complete.job,started_at:at(0),finished_at:at(0)},reviewedAt:at(0)});
 ordered(zero);assert.equal(zero.elapsedSeconds,0);assert.equal(zero.estimated,false);
 assert.equal(timingDuration(0),'0分钟');assert.equal(timingDuration(20),'不足1分钟');assert.equal(timingDuration(90061),'1天1小时1分钟');
});

test('each missing event is inferred without losing cumulative time or rewriting source data',()=>{
 for(const field of ['scene','input','started_at','finished_at','review']){
  const data=structuredClone(complete);
  if(field==='scene')delete data.sceneCreatedAt;
  else if(field==='input')delete data.input.registered_at;
  else if(field==='review')delete data.reviewedAt;
  else delete data.job[field];
  const before=structuredClone(data),value=buildTiming(data);
  ordered(value);assert.ok(value.elapsedSeconds>0);assert.equal(value.estimated,true);assert.equal(value.complete,true);
  assert.ok(Date.parse(value.stages[3].end)<=Date.parse(data.now));assert.deepEqual(data,before);
 }
});

test('an old estimated input timestamp cannot override actual model and review dates',()=>{
 const value=buildTiming({...complete,input:{registered_at:at(50),registered_at_estimated:true}});
 ordered(value);assert.equal(value.stages[2].start,at(25));assert.equal(value.stages[2].end,at(35));
 assert.equal(value.stages[2].estimated,false);assert.equal(value.stages[3].end,at(40));
});

test('submitted and queued builds retain planned finish without manufacturing completion',()=>{
 for(const state of ['queued','running']){
  const value=buildTiming({sceneCreatedAt:at(0),job:{state,created_at:at(25)},now:at(28)});
  ordered(value);assert.deepEqual(value.stages.map(s=>s.state),['complete','complete','current','pending']);
  assert.equal(value.complete,false);assert.equal(value.elapsedSeconds,28*60);assert.equal(value.remainingSeconds,12*60);
 }
 const demo={stages:[0,1,2,3].map(i=>({start:at(i*5),end:at((i+1)*5),estimated:true}))};
 const value=buildTiming({sceneCreatedAt:at(0),job:{state:'succeeded',created_at:at(10),finished_at:at(15),demo_timeline:demo},now:at(30)});
 ordered(value);assert.equal(value.complete,false);assert.equal(value.stages[3].state,'current');assert.equal(value.stages[3].overdue,true);
});

test('old completed builds with sparse dates stay historical and use the scene creation anchor',()=>{
 const value=buildTiming({sceneCreatedAt:at(0),job:{state:'succeeded',created_at:at(1)},selected:true,now:at(2)});
 ordered(value);assert.equal(value.elapsedSeconds,120);assert.equal(value.stages.at(-1).end,at(2));assert.equal(value.estimated,true);
 const built=buildTiming({sceneCreatedAt:at(0),job:{state:'succeeded',created_at:at(1)},now:at(2)});
 ordered(built);assert.equal(built.elapsedSeconds,120);assert.equal(built.complete,false);
});

test('failed work stops its clock and never forecasts a successful finish',()=>{
 for(const state of ['failed','interrupted','views_failed']){
  const value=buildTiming({sceneCreatedAt:at(0),job:{state,created_at:at(25),started_at:at(26),finished_at:at(28)},modelReady:state==='views_failed',now:at(60)});
  ordered(value);assert.equal(value.elapsedSeconds,28*60);assert.equal(value.remainingSeconds,0);assert.equal(value.stopped,true);
  assert.equal(value.complete,false);assert.equal(value.stages[2].state,'stopped');
 }
 const missingEnd=buildTiming({sceneCreatedAt:at(0),job:{state:'failed',created_at:at(25),finished_at:at(100)},now:at(60)});
 ordered(missingEnd);assert.equal(missingEnd.elapsedSeconds,60*60);assert.equal(missingEnd.stages[2].endSource,'inferred');
 const reversedStop=buildTiming({sceneCreatedAt:at(20),job:{state:'failed',created_at:at(100),finished_at:at(10)},now:at(60)});
 ordered(reversedStop);assert.equal(reversedStop.warnings,true);assert.equal(reversedStop.elapsedSeconds,40*60);
});

test('invalid, future and reversed records fall back visibly without negative or invalid durations',()=>{
 for(const job of [{state:'succeeded',created_at:'bad',started_at:at(25),finished_at:at(10)},
  {state:'succeeded',created_at:at(25),started_at:at(200),finished_at:'bad'}]){
  const value=buildTiming({sceneCreatedAt:at(20),input:{registered_at:at(10)},job,selected:true,now:at(60)});
  ordered(value);assert.equal(value.warnings,true);assert.equal(value.estimated,true);
 }
 assert.throws(()=>buildTiming({now:'bad'}),/invalid_timing_clock/);
});

test('unrecorded old scene and over-reference preparation still have complete timing estimates',()=>{
 const unknown=buildTiming({now:at(60)});ordered(unknown);assert.equal(unknown.startSource,'inferred');assert.equal(unknown.totalSeconds,40*60);
 const late=buildTiming({sceneCreatedAt:at(0),now:at(120)});ordered(late);
 assert.equal(late.elapsedSeconds,120*60);assert.equal(late.remainingSeconds,20*60);assert.equal(late.stages[0].overdue,true);
 assert.equal(late.stages[1].start,at(120));
});

test('all sparse timestamp combinations preserve order, finite totals and original completion state',()=>{
 for(let mask=0;mask<64;mask++)for(const state of ['queued','running','succeeded','failed']){
  const value=buildTiming({sceneCreatedAt:mask&1?at(0):undefined,input:mask&2?{registered_at:at(20)}:undefined,
   job:{state,created_at:mask&4?at(24):undefined,started_at:mask&8?at(25):undefined,finished_at:mask&16?at(35):undefined},
   selected:!!(mask&32),now:at(60)});
  ordered(value);assert.equal(value.complete,!!(mask&32));
 }
});
