import test from 'node:test';
import assert from 'node:assert/strict';
import {fileAppendQuery,parseUpgradeReport,versionComparison} from '../../apps/workbench/src/layout/data-upgrade-contract.ts';
import {parseResourceReport} from '../../apps/workbench/src/layout/data-catalog-contract.ts';

const project='project-'+'a'.repeat(16),resource='resource-'+'b'.repeat(32),old='c'.repeat(64),next='d'.repeat(64);
const snapshot=version=>({label:version===old?'控制网一版.csv':'控制网二版.csv',kind:'resource_file',resource_type:'reference',source_version:{version_id:version,reference_kind:'source_metadata',format:'csv',bytes:100,created_at:'2026-11-25T00:00:00Z'},is_base:true,payload_available:true});
const use={id:'use-'+'e'.repeat(32),resource_id:resource,version_id:old,grant_id:'grant-'+'f'.repeat(32),grant_revision:1,revision:1,project_id:project,space_id:null,purpose:'控制网参考',status:'active',use_mode:'reference',coordinate_status:'not_applied',updated_at:'2026-11-25T00:00:00Z'};
const grant={id:'grant-'+'1'.repeat(32),resource_id:resource,version_id:next,revision:1,target_kind:'project',target_project_id:project,allow_download:true,expires_at:null,status:'active'};
const report={profile:'cospace.reference-upgrade/0.1',workspace_id:'ws-demo',use,current:snapshot(old),candidates:[{grant,snapshot:snapshot(next)}],total:1,offset:0,limit:20,next_offset:null};

test('upgrade comparison requires matching use, project, resource, granted version and page',()=>{
 assert.equal(parseUpgradeReport(report,use,'ws-demo',0).candidates.length,1);
 for(const patch of [{workspace_id:'foreign'},{use:{...use,project_id:'project-'+'2'.repeat(16)}},{use:{...use,space_id:'space-'+'2'.repeat(16)}},{use:{...use,revision:0}},{use:{...use,status:'unlinked'}},{current:snapshot(next)},{offset:20},{limit:100},{total:0},{next_offset:20}])assert.throws(()=>parseUpgradeReport({...report,...patch},use,'ws-demo',0));
 for(const patch of [{resource_id:'resource-'+'2'.repeat(32)},{version_id:old},{target_project_id:'project-'+'2'.repeat(16)},{status:'revoked'},{revision:0}])assert.throws(()=>parseUpgradeReport({...report,candidates:[{grant:{...grant,...patch},snapshot:snapshot(next)}]},use,'ws-demo',0));
 assert.throws(()=>parseUpgradeReport({...report,candidates:[{grant,snapshot:{...snapshot(next),href:'/data?space=private'}}]},use,'ws-demo',0));
});

test('append carries concurrency preconditions and no mutable ownership or scene claims',()=>{
 const item={resource_id:resource,source_version:{version_id:old},revision:2};
 const q=fileAppendQuery(item,'control.csv','追加原件','a'.repeat(32));
 assert.equal(q.get('resource_id'),resource);assert.equal(q.get('expected_version'),old);assert.equal(q.get('expected_revision'),'2');
 for(const field of ['owner_project_id','owner_kind','is_base','space_id','workspace_id','actor'])assert.equal(q.has(field),false);
 const rows=versionComparison(snapshot(old),snapshot(next));
 assert.deepEqual(rows[0],['名称','控制网一版.csv','控制网二版.csv']);
 assert.deepEqual(rows.at(-1),['版本',old.slice(0,12),next.slice(0,12)]);
});

test('file directory accepts multiple retained versions and rejects invalid version counts',()=>{
 const item={key:resource,record_id:resource,resource_id:resource,kind:'resource_file',space_id:null,space_name:null,href:null,label:'控制网.csv',registered:true,version_registered:true,version_count:2,revision:2,resource_type:'reference',project_id:project,owner_kind:'project',owner_project_id:project,source_version:snapshot(next).source_version};
 const scope={workspace:'ws-demo',project,space:'',category:'all'},value={profile:'cospace.data-resources/0.1',workspace_id:'ws-demo',project_id:project,space_id:null,category:'all',items:[item],spaces:[],total:1,status:'ready',source_files_rechecked:false};
 assert.equal(parseResourceReport(value,scope).items[0].version_count,2);
 for(const count of [0,1001,1.5,'2'])assert.throws(()=>parseResourceReport({...value,items:[{...item,version_count:count}]},scope));
});
