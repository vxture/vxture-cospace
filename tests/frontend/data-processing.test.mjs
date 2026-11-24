import test from 'node:test';
import assert from 'node:assert/strict';
import {parseProcessing,parseGovernance,validateGovernanceResult} from '../../apps/workbench/src/layout/data-processing-contract.ts';
import {parseResourceReport} from '../../apps/workbench/src/layout/data-catalog-contract.ts';

const resource='resource-'+'a'.repeat(32),digest='b'.repeat(64),input='input-'+'c'.repeat(16);
const nodes=[{key:'input:'+input,kind:'input',record_id:input,state:'registered',metadata_sha256:null},{key:'job:build-one',kind:'job',record_id:'build-one',state:'succeeded',metadata_sha256:null},{key:'candidate:build-one',kind:'candidate',record_id:'build-one',state:'metadata_matched',metadata_sha256:digest}];
const processing={profile:'cospace.resource-processing/0.1',workspace_id:'ws',resource_id:resource,focus:nodes[0].key,status:'ready',nodes,edges:[{from:nodes[1].key,to:nodes[0].key,relation:'consumes',status:'matched'},{from:nodes[2].key,to:nodes[1].key,relation:'produced_by',status:'matched'}],issues:[],source_files_rechecked:false,jobs_polled:false};
const governance={profile:'cospace.resource-governance/0.1',workspace_id:'ws',resource_id:resource,state:'active',revision:0,snapshot:digest,impact:{scope:'workspace',linked_references:0,active_grants:0},actions:[{action:'archive',allowed:true,blockers:[]},{action:'restore',allowed:false,blockers:[]}],physical_delete_supported:false,last_change:null};

test('processing permits only bounded saved nodes and explicit evidence status',()=>{
 assert.equal(parseProcessing(processing,'ws',resource).nodes.length,3);
 assert.equal(parseProcessing({...processing,status:'partial',edges:[{from:nodes[1].key,to:null,relation:'consumes',status:'unresolved'}]},'ws',resource).status,'partial');
 for(const change of [{workspace_id:'other'},{resource_id:'other'},{jobs_polled:true},{source_files_rechecked:true},{nodes:[...nodes,nodes[0]]},{focus:'foreign'},{status:'not_applicable'},{edges:[{from:nodes[1].key,to:'private',relation:'consumes',status:'matched'}]},{edges:[{from:nodes[1].key,to:null,relation:'consumes',status:'matched'}]},{nodes:[{...nodes[2],state:'failed'}]},{issues:['missing']}])assert.throws(()=>parseProcessing({...processing,...change},'ws',resource));
});
test('archive permission must agree with workspace-wide impact and lifecycle state',()=>{
 assert.equal(parseGovernance(governance,'ws',resource).state,'active');
 for(const change of [{workspace_id:'foreign'},{snapshot:'short'},{physical_delete_supported:true},{impact:{...governance.impact,scope:'visible_only'}},{impact:{...governance.impact,linked_references:1}},{state:'archived'},{actions:[governance.actions[0],governance.actions[0]]},{last_change:{reason:'x',updated_at:'invalid'}}])assert.throws(()=>parseGovernance({...governance,...change},'ws',resource));
 const blocked={...governance,impact:{scope:'workspace',linked_references:1,active_grants:0},actions:[{action:'archive',allowed:false,blockers:['resource_has_references']},governance.actions[1]]};
 assert.equal(parseGovernance(blocked,'ws',resource).actions[0].allowed,false);
});
test('lifecycle filter is request-scoped and never accepts a silent different response',()=>{
 const r={profile:'cospace.data-resources/0.1',workspace_id:'ws',category:'all',project_id:null,space_id:null,lifecycle:'archived',items:[],spaces:[],total:0,status:'ready',source_files_rechecked:false};
 const scope={workspace:'ws',category:'all',project:'',space:'',lifecycle:'archived'};
 assert.equal(parseResourceReport(r,scope).total,0);
 assert.throws(()=>parseResourceReport({...r,lifecycle:'all'},scope));
});

test('governance mutation confirms exact resource, transition and revision',()=>{
 const value={resource_id:resource,action:'archive',after:{resource_id:resource,state:'archived',revision:1}};
 assert.doesNotThrow(()=>validateGovernanceResult(value,resource,'archive',0));
 for(const change of [{resource_id:'other'},{action:'restore'},{after:{...value.after,resource_id:'other'}},{after:{...value.after,revision:0}},{after:{...value.after,state:'active'}}])assert.throws(()=>validateGovernanceResult({...value,...change},resource,'archive',0));
});
