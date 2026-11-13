import {test} from 'node:test';
import assert from 'node:assert/strict';
import {identityEntryState,subscriptionEntryState} from '../../apps/workbench/src/layout/entry-state.ts';

const user={subject:'member',org_id:'org',workspace_id:'workspace'};
const confirmed={authenticated:true,authority_state:'confirmed',user};
const signedOut={authenticated:false,authority_state:'signed_out'};
const subscription={application_authorized:true,business_allowed:false,status:null};

test('entry waits for session and distinguishes unreadable sessions from signed-out users',()=>{
 assert.equal(identityEntryState(null),'restoring');
 assert.equal(identityEntryState(null,{failed:true}),'unavailable');
 assert.equal(identityEntryState(signedOut),'signin');
 assert.equal(identityEntryState(signedOut,{signedOut:true}),'signed-out');
 // A marker from a previous logout cannot override a real, confirmed account.
 assert.equal(identityEntryState(confirmed,{signedOut:true}),'identity');
});

test('only server-confirmed identity reaches subscription UI',()=>{
 assert.equal(identityEntryState(confirmed),'identity');
 assert.equal(identityEntryState({...confirmed,authority_state:'cached',authority_ready:true}),'identity');
 for(const session of [
  {...confirmed,authority_state:'cached',authority_ready:false},
  {...confirmed,authority_state:'unavailable',authority_ready:true},
  {...confirmed,authority_state:'checking'},
  {...confirmed,user:undefined},
 ])assert.equal(identityEntryState(session),'recovery');
});

test('working tab recovers instead of presenting an ordinary login or logout screen',()=>{
 assert.equal(identityEntryState(signedOut,{preserveWork:true,signedOut:true}),'recovery');
 assert.equal(identityEntryState({...confirmed,authority_state:'unavailable'},{preserveWork:true}),'recovery');
 assert.equal(identityEntryState(confirmed,{preserveWork:true}),'identity');
});

test('unreadable authorization is never interpreted as missing or expired subscription',()=>{
 assert.equal(subscriptionEntryState(null),'checking-access');
 assert.equal(subscriptionEntryState(null,true),'access-unavailable');
 assert.equal(subscriptionEntryState({...subscription,status:'expired'},true),'access-unavailable');
});

test('platform application denial stays distinct from subscription and workspace decisions',()=>{
 assert.equal(subscriptionEntryState({...subscription,application_authorized:false,status:'active'}),'unassigned');
 assert.equal(subscriptionEntryState({...subscription,application_authorized:false,status:'expired'}),'unassigned');
 assert.equal(subscriptionEntryState(subscription),'subscription');
});

test('only explicit expiry is shown as expiry and platform allowance always wins over billing status',()=>{
 assert.equal(subscriptionEntryState({...subscription,status:'expired'}),'expired');
 for(const status of ['active','trialing','expiring','suspended','cancelled','overdue','future',null]){
  assert.equal(subscriptionEntryState({...subscription,status}),'subscription');
  assert.equal(subscriptionEntryState({...subscription,status,business_allowed:true}),'connected');
 }
 assert.equal(subscriptionEntryState({...subscription,status:'expired',business_allowed:true}),'connected');
});

test('retry results replace failed and denied display with current platform facts',()=>{
 const sequence=[
  subscriptionEntryState(null,true),
  subscriptionEntryState({...subscription,application_authorized:false}),
  subscriptionEntryState({...subscription,business_allowed:true,status:'active'}),
 ];
 assert.deepEqual(sequence,['access-unavailable','unassigned','connected']);
});
