import {test} from 'node:test';
import assert from 'node:assert/strict';
import {phoneParts,accountVerification} from '../../apps/workbench/src/layout/account-profile.ts';

test('mainland phone matches platform country-prefix and 3-4-4 grouping',()=>{
 for(const phone of ['13800000000','+86 138 0000 0000','86(138)0000-0000'])assert.deepEqual(phoneParts(phone),{prefix:'+86',number:'138 0000 0000'});
 assert.deepEqual(phoneParts('+44 20 1234 5678'),{prefix:'',number:'+44 20 1234 5678'});
});
test('status describes verified contact only, without inventing identity certification',()=>{
 assert.equal(accountVerification(),undefined);
 assert.equal(accountVerification({phone:'13800000000',phone_verified:false}),undefined);
 assert.deepEqual(accountVerification({phone:'13800000000',phone_verified:true}),{label:'手机已验证',verified:true});
 assert.deepEqual(accountVerification({email:'person@example.test',email_verified:true}),{label:'邮箱已验证',verified:true});
});
