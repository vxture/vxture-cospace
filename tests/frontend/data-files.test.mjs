import test from 'node:test';
import assert from 'node:assert/strict';
import {referenceFileError,fileUploadQuery} from '../../apps/workbench/src/layout/data-file-contract.ts';
import {parseResourceReport,resourceOwnerLabel,resourceFileDownload} from '../../apps/workbench/src/layout/data-catalog-contract.ts';

const project='project-'+'a'.repeat(16),resource='resource-'+'b'.repeat(32),version='c'.repeat(64);
const item={key:resource,record_id:resource,resource_id:resource,kind:'resource_file',space_id:null,space_name:null,href:null,label:'园区控制网.csv',registered:true,version_registered:true,version_count:1,revision:1,can_manage:true,resource_type:'reference',project_id:project,owner_kind:'project',owner_project_id:project,owner_project_name:'基础测绘',source_version:{version_id:version,reference_kind:'source_metadata',bytes:100,created_at:'2026-11-25T00:00:00Z'}};
const scope={workspace:'ws-a',project,space:'',category:'all'};
const report={profile:'cospace.data-resources/0.1',workspace_id:'ws-a',project_id:project,space_id:null,category:'all',items:[item],spaces:[],total:1,status:'ready',source_files_rechecked:false};

test('scene-independent files require explicit owner, fixed version and no fabricated scene URL',()=>{
 assert.equal(parseResourceReport(report,scope).items.length,1);
 const common={...item,owner_kind:'workspace',owner_project_id:null,owner_project_name:null,project_id:null};
 assert.equal(resourceOwnerLabel(common),'工作区共用');
 assert.equal(parseResourceReport({...report,project_id:null,items:[common]},{...scope,project:''}).items.length,1);
 assert.equal(resourceFileDownload(item),`/api/data-files/download?resource_id=${resource}&version_id=${version}`);
 for(const invalid of [{href:'#data?space=private'},{space_id:'space-'+'f'.repeat(16)},{owner_kind:'workspace'},{owner_kind:'project',owner_project_id:null},{owner_kind:'unassigned'},{owner_project_id:'project-'+'d'.repeat(16)},{registered:false},{version_registered:false},{resource_id:'../../private'},{source_version:{version_id:'bad'}}])assert.throws(()=>parseResourceReport({...report,items:[{...item,...invalid}]},scope));
 assert.throws(()=>parseResourceReport(report,{...scope,placement:'project'}));
 assert.equal(parseResourceReport({...report,placement:'project',ownership:'owned'},{...scope,placement:'project',ownership:'owned'}).total,1);
});

test('reference upload uses bounded files and never carries scene/workspace/actor claims',()=>{
 assert.equal(referenceFileError({name:'控制网.CSV',size:10}),'');
 for(const bad of [{name:'x.csv',size:0},{name:'x.csv',size:32*1024*1024+1},{name:'../x.csv',size:10},{name:'x.exe',size:10},{name:'x\n.csv',size:10}])assert.notEqual(referenceFileError(bad),'');
 const fields={ownerKind:'workspace',project,name:'控制网.csv',base:true,reason:'基础控制网',requestId:'d'.repeat(32)};
 const query=fileUploadQuery(fields);
 assert.equal(query.get('owner_kind'),'workspace');assert.equal(query.has('owner_project_id'),false);
 for(const key of ['space_id','workspace_id','actor'])assert.equal(query.has(key),false);
 assert.equal(fileUploadQuery({...fields,ownerKind:'project'}).get('owner_project_id'),project);
});
