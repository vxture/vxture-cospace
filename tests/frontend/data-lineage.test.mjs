import test from 'node:test';
import assert from 'node:assert/strict';
import {parseResourceTrace} from '../../apps/workbench/src/layout/data-lineage-contract.ts';

const resource='resource-'+'a'.repeat(32),version='b'.repeat(64),project='project-'+'c'.repeat(16);
const report={profile:'cospace.resource-lineage/0.1',workspace_id:'ws-a',resource_id:resource,project_id:null,view:'source',resource:{label:'园区控制网',kind:'resource_file',owner:'基础测绘项目'},source:{state:'current',version_id:version,space_name:null,href:null},versions:[{version_id:version,reference_kind:'source_metadata',created_at:'2026-11-25T00:00:00Z',format:'csv',bytes:120,recorded_at:'2026-11-25T00:00:00Z',current:true,snapshot_saved:false}],references:[],summary:{linked_references:0,effective_references:0,historical_references:0,projects:0,scope:'visible_only'},impact:{scope:'visible_only',retention_required:false,global_assessment:'not_assessed',physical_delete_supported:false},total:0,offset:0,limit:10,next_offset:null,status:'ready',source_files_rechecked:false};
const scope={workspace:'ws-a',resource,offset:0};

test('trace accepts fixed versions with explicit visible-only impact and missing source state',()=>{
 assert.equal(parseResourceTrace(report,scope).versions.length,1);
 const missing={...report,status:'partial',source:{...report.source,state:'unavailable',version_id:null},versions:report.versions.map(v=>({...v,current:null}))};
 assert.equal(parseResourceTrace(missing,scope).status,'partial');
});
test('trace rejects cross-workspace/resource/project and unsafe source links',()=>{
 for(const values of [{workspace_id:'foreign'},{resource_id:'resource-'+'d'.repeat(32)},{project_id:project},{offset:10},{source_files_rechecked:true},{source:{...report.source,href:'https://external.test/private'}}])assert.throws(()=>parseResourceTrace({...report,...values},scope));
 for(const values of [{scope:'all'},{global_assessment:'safe'},{physical_delete_supported:true},{retention_required:true}])assert.throws(()=>parseResourceTrace({...report,impact:{...report.impact,...values}},scope));
 assert.throws(()=>parseResourceTrace({...report,summary:{...report.summary,linked_references:1}},scope));
});
test('reference trace forbids source locations and assertions about unseen current versions',()=>{
 const consumer={...report,project_id:project,view:'reference',source:{state:'restricted',version_id:null,space_name:null,href:null},versions:report.versions.map(v=>({...v,current:null,recorded_at:null,snapshot_saved:true}))};
 const currentScope={...scope,project};
 assert.equal(parseResourceTrace(consumer,currentScope).view,'reference');
 for(const source of [{...consumer.source,href:'#data?space=private'},{...consumer.source,space_name:'private'},{...consumer.source,version_id:version}])assert.throws(()=>parseResourceTrace({...consumer,source},currentScope));
 assert.throws(()=>parseResourceTrace({...consumer,versions:report.versions},currentScope));
});
