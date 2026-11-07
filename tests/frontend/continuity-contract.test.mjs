import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DraftRegistry} from '../../apps/workbench/src/layout/draft-registry.ts';
import {sessionScopeKey,sessionConfirmed} from '../../apps/workbench/src/layout/session-continuity.ts';

test('save waits for all receipts and stops on failure without repeating an acknowledged save',async()=>{
 const registry=new DraftRegistry(),first=Symbol(),second=Symbol();let calls=[];
 registry.set(first,{label:'first',save:async()=>{calls.push('first');return true;}});
 registry.set(second,{label:'second',save:async()=>{calls.push('second');return false;}});
 assert.equal(await registry.saveAll(),false);assert.deepEqual(calls,['first','second']);
 assert.equal(registry.entries.has(first),false);assert.equal(registry.entries.has(second),true);
 registry.set(second,{label:'second',save:async()=>{calls.push('retry');return true;}});
 assert.equal(await registry.saveAll(),true);assert.deepEqual(calls,['first','second','retry']);
});

test('scope reset invalidates an outstanding save acknowledgement',async()=>{
 const registry=new DraftRegistry();let done;
 registry.set(Symbol(),{label:'old scope',save:()=>new Promise(resolve=>done=resolve)});
 const saving=registry.saveAll();registry.clear();done(true);
 assert.equal(await saving,false);assert.equal(registry.entries.size,0);
});

test('draft without admissible save never creates a write as a navigation side effect',async()=>{
 const registry=new DraftRegistry();let calls=0;
 registry.set(Symbol(),{label:'needs explicit review',canSave:false,save:async()=>{calls++;return true;}});
 assert.equal(await registry.saveAll(),false);assert.equal(calls,0);
 registry.discardAll();assert.equal(calls,0);assert.equal(registry.entries.size,0);
});

test('each tab registry is independent and identity includes organization, workspace and subject',()=>{
 const first=new DraftRegistry(),second=new DraftRegistry();first.set(Symbol(),{label:'first'});
 assert.equal(second.entries.size,0);
 const session={authenticated:true,authority_state:'confirmed',user:{org_id:'org',workspace_id:'workspace',subject:'one'}};
 assert.equal(sessionConfirmed(session),true);assert.equal(sessionConfirmed({...session,authority_state:'unavailable'}),false);
 assert.equal(sessionScopeKey({...session,authenticated:false}),'');
 for(const field of ['org_id','workspace_id','subject'])assert.notEqual(sessionScopeKey(session),sessionScopeKey({...session,user:{...session.user,[field]:'different'}}));
});

test('all drafts are checked before the first write and discard resets every editor without saving',async()=>{
 const registry=new DraftRegistry();let writes=0,resets=[];
 registry.set(Symbol(),{label:'supported',save:async()=>{writes++;return true;},discard:()=>resets.push('supported')});
 registry.set(Symbol(),{label:'review required',discard:()=>resets.push('review required')});
 assert.equal(await registry.saveAll(),false);assert.equal(writes,0);
 registry.discardAll();assert.deepEqual(resets,['supported','review required']);assert.equal(registry.entries.size,0);
});
