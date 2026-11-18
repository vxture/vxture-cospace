import {test} from 'node:test';
import assert from 'node:assert/strict';
import {phoneParts,accountVerification,organizationContext} from '../../apps/workbench/src/layout/account-profile.ts';

test('header uses verified short name and workspace while panel keeps full name',()=>{
 const context=organizationContext({org_name:'如影智能科技有限公司',org_short_name:'如影智能',org_type:'organization',workspace_name:'场景协作'});
 assert.equal(context.label,'如影智能 · 场景协作');
 assert.equal(context.fullName,'如影智能科技有限公司');
 assert.equal(context.typeLabel,'组织');
 assert.equal(organizationContext({org_name:'全称',org_short_name:'  ',workspace_name:'  '}).label,'全称 · 工作区名称待补全');
 assert.equal(organizationContext({org_type:'personal'}).typeLabel,'个人');
 assert.equal(organizationContext({org_type:'unknown'}).typeLabel,'类型待补全');
});

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
