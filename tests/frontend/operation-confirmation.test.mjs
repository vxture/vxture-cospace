import test from 'node:test';
import assert from 'node:assert/strict';
import {OperationConfirmationStore} from '../../apps/workbench/src/layout/operation-confirmation-store.ts';
import {collectionImpact,reducedDeviceRelations} from '../../apps/workbench/src/layout/operation-impact.ts';
const details={verb:'移除',target:'对象 A',consequence:'仅修改当前草稿'};

test('opening and cancelling a confirmation never execute its mutation',async()=>{
 const store=new OperationConfirmationStore(),owner=Symbol();let writes=0;
 const result=store.request(owner,details,()=>writes++),old=store.snapshot();
 assert.equal(writes,0);store.cancel(owner);assert.equal(await result,false);
 await store.commit(old);assert.equal(writes,0);assert.equal(store.snapshot(),null);
});
test('another owner cannot close or replace a pending operation',async()=>{
 const store=new OperationConfirmationStore(),owner=Symbol();let writes=0;
 const result=store.request(owner,details,()=>writes++),pending=store.snapshot();
 assert.equal(await store.request(Symbol(),details,()=>writes++),false);
 store.cancel(Symbol());assert.equal(store.snapshot(),pending);
 await store.commit(pending);assert.equal(await result,true);assert.equal(writes,1);
});
test('double activation submits once and success clears the operation',async()=>{
 const store=new OperationConfirmationStore();let finish,writes=0;
 const result=store.request(Symbol(),details,()=>{writes++;return new Promise(resolve=>finish=resolve);});
 const pending=store.snapshot(),first=store.commit(pending);await store.commit(pending);
 assert.equal(writes,1);finish();await first;assert.equal(await result,true);assert.equal(store.snapshot(),null);
});
test('failed and boolean-failed actions remain open until explicit cancellation',async()=>{
 for(const execute of [()=>{throw Error('修订已变化');},async()=>false]){
  const store=new OperationConfirmationStore(),result=store.request(Symbol(),details,execute),pending=store.snapshot();
  await assert.rejects(store.commit(pending));assert.equal(store.snapshot(),pending);assert.equal(pending.running,false);
  store.cancel();assert.equal(await result,false);
 }
});
test('failed action can be explicitly retried, never automatically replayed',async()=>{
 const store=new OperationConfirmationStore();let writes=0;
 const result=store.request(Symbol(),details,()=>{if(++writes===1)throw Error('未受理');}),pending=store.snapshot();
 await assert.rejects(store.commit(pending));assert.equal(writes,1);
 await store.commit(pending);assert.equal(await result,true);assert.equal(writes,2);
});
test('unmet preconditions block writes and context invalidation rejects stale callbacks',async()=>{
 const store=new OperationConfirmationStore();let writes=0;
 const result=store.request(Symbol(),{...details,preconditions:[{label:'引用完整',met:false,unknown:true}]},()=>writes++),pending=store.snapshot();
 await store.commit(pending);assert.equal(writes,0);
 store.cancel();assert.equal(await result,false);await store.commit(pending);assert.equal(writes,0);
});
test('late receipt after a scope reset cannot close a new operation',async()=>{
 const store=new OperationConfirmationStore();let finish;
 const oldResult=store.request(Symbol(),details,()=>new Promise(resolve=>finish=resolve)),old=store.snapshot(),commit=store.commit(old);
 store.cancel();assert.equal(await oldResult,false);
 const nextResult=store.request(Symbol(),{...details,target:'对象 B'},()=>{}),next=store.snapshot();
 finish();await commit;assert.equal(store.snapshot(),next);await store.commit(next);assert.equal(await nextResult,true);
});
test('successful owner unmount preserves the save-and-leave receipt',async()=>{
 const store=new OperationConfirmationStore(),owner=Symbol();let finish;
 const result=store.request(owner,details,()=>new Promise(resolve=>finish=resolve)),pending=store.snapshot();
 const commit=store.commit(pending);store.cancel(owner);assert.equal(store.snapshot(),null);
 finish(true);await commit;assert.equal(await result,true);
});
test('owner unmount followed by failure settles navigation without an orphan promise',async()=>{
 const store=new OperationConfirmationStore(),owner=Symbol();let finish;
 const result=store.request(owner,details,()=>new Promise(resolve=>finish=resolve)),pending=store.snapshot();
 const commit=store.commit(pending);store.cancel(owner);finish(false);
 await assert.rejects(commit);assert.equal(await result,false);
});
test('identity reset after owner unmount still invalidates an outstanding save',async()=>{
 const store=new OperationConfirmationStore(),owner=Symbol();let finish;
 const result=store.request(owner,details,()=>new Promise(resolve=>finish=resolve)),pending=store.snapshot();
 const commit=store.commit(pending);store.cancel(owner);store.cancel();finish(true);
 await commit;assert.equal(await result,false);
});
test('impact summaries distinguish additions, replacements and full removal',()=>{
 const before=[{id:'a',value:1},{id:'b',value:2}];
 assert.equal(collectionImpact(before,[{id:'b',value:3},{id:'c',value:4}],x=>x.id),'新增 1 项、修改 1 项、移除 1 项');
 assert.equal(collectionImpact(before,[],x=>x.id),'新增 0 项、修改 0 项、移除 2 项');
});
test('device reductions include removed scenes, purposes and delivery modes, excluding additions',()=>{
 const relation={space_id:'a',purposes:['collect','use'],usage_modes:['online','offline']};
 assert.equal(reducedDeviceRelations([relation],[]),1);
 assert.equal(reducedDeviceRelations([relation],[{...relation,purposes:['collect']}]),1);
 assert.equal(reducedDeviceRelations([relation],[{...relation,usage_modes:['online']}]),1);
 assert.equal(reducedDeviceRelations([relation],[relation,{...relation,space_id:'b'}]),0);
 assert.equal(reducedDeviceRelations([relation],[{...relation,purposes:['use','collect'],usage_modes:['offline','online']}]),0);
});
