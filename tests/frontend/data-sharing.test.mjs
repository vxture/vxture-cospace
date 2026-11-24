import test from 'node:test';
import assert from 'node:assert/strict';
import {parseSharingReport} from '../../apps/workbench/src/layout/data-sharing-contract.ts';
import {parseResourceReport} from '../../apps/workbench/src/layout/data-catalog-contract.ts';
const project='project-'+'b'.repeat(16),resource='resource-'+'a'.repeat(32),version='c'.repeat(64);
const grant={id:'grant-'+'d'.repeat(32),resource_id:resource,version_id:version,revision:1,target_kind:'project',target_project_id:project,allow_download:true,status:'active',expires_at:null};
const snapshot={label:'园区控制网',kind:'attachment',resource_type:'reference',source_version:{version_id:version,reference_kind:'source_metadata',created_at:null},is_base:true,payload_available:true};
const use={id:'use-'+'e'.repeat(32),resource_id:resource,version_id:version,grant_id:grant.id,grant_revision:1,revision:1,project_id:project,space_id:null,purpose:'底图参考',status:'active',access_status:'active',allow_download:true,snapshot,use_mode:'reference',coordinate_status:'not_applied'};
const report=(view,items)=>({profile:'cospace.resource-sharing/0.1',workspace_id:'ws-a',view,project_id:project,resource_id:null,items,total:items.length,next_offset:null});
test('sharing response fixes workspace, target project, version and reference scope',()=>{
 const available={grant,snapshot,reference_revision:0,reference_status:null};
 assert.equal(parseSharingReport(report('available',[available]),{workspace:'ws-a',view:'available',project}).total,1);
 assert.equal(parseSharingReport(report('uses',[use]),{workspace:'ws-a',view:'uses',project}).total,1);
 for(const mutation of [{workspace_id:'other'},{project_id:'other'},{view:'grants'}])assert.throws(()=>parseSharingReport({...report('available',[available]),...mutation},{workspace:'ws-a',view:'available',project}));
 for(const invalid of [{...available,grant:{...grant,target_project_id:'project-'+'f'.repeat(16)}},{...available,snapshot:{...snapshot,source_version:{...snapshot.source_version,version_id:'f'.repeat(64)}}},{...available,snapshot:{...snapshot,href:'#data?space=private'}}])assert.throws(()=>parseSharingReport(report('available',[invalid]),{workspace:'ws-a',view:'available',project}));
});
test('external rows contain fixed authorized uses without a private source-scene link',()=>{
 const row={key:resource,record_id:resource,resource_id:resource,kind:'attachment',label:'控制网',href:null,space_id:null,space_name:null,external:true,registered:true,can_manage:false,uses:[use],source_version:snapshot.source_version};
 const directory={profile:'cospace.data-resources/0.1',workspace_id:'ws-a',category:'all',project_id:project,space_id:null,items:[row],spaces:[],total:1,status:'ready',source_files_rechecked:false};
 const scope={workspace:'ws-a',project,space:'',category:'all'};
 assert.equal(parseResourceReport(directory,scope).items[0].uses[0].version_id,version);
 for(const values of [{href:'#data?space=private'},{space_id:'private'},{can_manage:true},{uses:[]},{uses:[{...use,project_id:'project-'+'f'.repeat(16)}]},{uses:[{...use,coordinate_status:'assumed_compatible'}]}])assert.throws(()=>parseResourceReport({...directory,items:[{...row,...values}]},scope));
 assert.equal(parseResourceReport({...directory,items:[{...row,uses:[{...use,access_status:'expired',allow_download:false}]}]},scope).items.length,1);
});
