import {test} from 'node:test';
import assert from 'node:assert/strict';
import {WorkspaceQueryStore} from '../../apps/workbench/src/layout/workspace-query-store.ts';
import {confirmationDeadline,requestSessionConfirmation} from '../../apps/workbench/src/layout/session-continuity.ts';

test('module switches and drawer reopen reuse one successful scope query',async()=>{
 let now=0,calls=0;const store=new WorkspaceQueryStore(()=>now),load=async()=>{calls++;return ['scene-a'];};
 await Promise.all([store.read('directory',load),store.read('directory',load)]);
 await store.read('directory',load);
 assert.equal(calls,1);assert.deepEqual(store.snapshot('directory').data,['scene-a']);
 now=15000;await store.read('directory',load);assert.equal(calls,2);
});
test('invalidation rejects old responses and clears data before replacement',async()=>{
 const store=new WorkspaceQueryStore();let finish;
 const first=store.read('scene-a',()=>new Promise(resolve=>{finish=resolve;}));
 await Promise.resolve();store.invalidate();
 assert.equal(store.snapshot('scene-a').data,null);
 await store.read('scene-a',async()=>({name:'new'}));finish({name:'old'});await first;
 assert.deepEqual(store.snapshot('scene-a').data,{name:'new'});
});
test('different scopes never share queries and failures never retain a grant-bearing response',async()=>{
 const first=new WorkspaceQueryStore(),second=new WorkspaceQueryStore();
 await first.read('directory',async()=>['private-scene']);assert.equal(second.snapshot('directory').data,null);
 first.invalidate();await first.read('directory',async()=>{throw new Error('denied');});
 assert.equal(first.snapshot('directory').data,null);assert.equal(first.snapshot('directory').error,'denied');
});

test('refresh updates the canonical shared key without cancelling other queries',async()=>{
 const store=new WorkspaceQueryStore();let finish;
 const unrelated=store.read('overview',()=>new Promise(resolve=>{finish=resolve;}));
 await store.read('directory',async()=>['old']);
 store.invalidate('directory');await store.read('directory',async()=>['new']);
 finish('kept');await unrelated;
 assert.deepEqual(store.snapshot('directory').data,['new']);
 assert.equal(store.snapshot('overview').data,'kept');
});
test('server session lifetime uses monotonic request start without extending it by network delay',()=>{
 assert.equal(confirmationDeadline(60,1000),61000);
 for(const value of [undefined,null,NaN,Infinity,'60',-5])assert.equal(confirmationDeadline(value,1000),1000);
});

test('normal confirmation sends only POST, while rotated CSRF recovers once',async()=>{
 const calls=[];
 const send=async(url,init)=>{calls.push([url,init?.method||'GET',init?.headers?.['X-CoSpace-CSRF']]);return Response.json({csrf:'new'});};
 assert.equal((await requestSessionConfirmation(send,'old',()=>true)).status,200);
 assert.deepEqual(calls,[['/api/auth/session','POST','old']]);
 calls.length=0;
 const rotated=async(url,init)=>{const result=await send(url,init);return calls.length===1?new Response(null,{status:403}):result;};
 assert.equal((await requestSessionConfirmation(rotated,'old',()=>true)).status,200);
 assert.deepEqual(calls,[['/api/auth/session','POST','old'],['/api/auth/session','GET',undefined],['/api/auth/session','POST','new']]);
});

test('scope change during recovery stops confirmation, and another denial never loops',async()=>{
 let valid=true;const calls=[];
 const send=async(url,init)=>{calls.push(init?.method||'GET');if(calls.length===2)valid=false;return new Response(null,{status:403});};
 assert.equal(await requestSessionConfirmation(send,'old',()=>valid),null);
 assert.deepEqual(calls,['POST','GET']);
 calls.length=0;valid=true;
 const denied=async(url,init)=>{calls.push(init?.method||'GET');return init?.method?new Response(null,{status:403}):Response.json({csrf:'new'});};
 assert.equal((await requestSessionConfirmation(denied,'old',()=>true)).status,403);
 assert.deepEqual(calls,['POST','GET','POST']);
});
