export type ProcessingNode={key:string;kind:'input'|'job'|'candidate'|'human_view'|'agent_view'|'publication';record_id:string;state:string;metadata_sha256:string|null};
export type ProcessingReport={profile:'cospace.resource-processing/0.1';workspace_id:string;resource_id:string;focus:string|null;status:'ready'|'partial'|'not_applicable';nodes:ProcessingNode[];edges:{from:string;to:string|null;relation:string;status:'matched'|'unresolved'}[];issues:string[];source_files_rechecked:false;jobs_polled:false};
export type GovernanceReport={profile:'cospace.resource-governance/0.1';workspace_id:string;resource_id:string;state:'active'|'archived';revision:number;snapshot:string;impact:{scope:'workspace';linked_references:number;active_grants:number};actions:{action:'archive'|'restore';allowed:boolean;blockers:string[]}[];physical_delete_supported:false;last_change:{reason:string;updated_at:string}|null};
const digest=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const count=(v:unknown)=>Number.isInteger(v)&&Number(v)>=0;
const kinds=['input','job','candidate','human_view','agent_view','publication'];
const relations=['consumes','produced_by','expresses','derived_from','published_from','output_unresolved'];
function validNode(n:ProcessingNode){
 if(!n||!kinds.includes(n.kind)||n.key!==n.kind+':'+n.record_id||n.metadata_sha256!==null&&!digest(n.metadata_sha256))return false;
 if(n.kind==='input')return /^input-[a-f0-9]{16}$/.test(n.record_id)&&n.state==='registered';
 if(n.kind==='publication')return /^preview-[a-f0-9]{16}$/.test(n.record_id)&&n.state==='fixed_record';
 if(!/^build-[A-Za-z0-9-]+$/.test(n.record_id))return false;
 if(n.kind==='job')return ['queued','running','succeeded','failed','interrupted','views_failed','unknown'].includes(n.state);
 return n.kind==='candidate'?n.state==='metadata_matched'&&digest(n.metadata_sha256):n.state==='declared'&&digest(n.metadata_sha256);
}
export function parseProcessing(value:unknown,workspace:string,resource:string):ProcessingReport{
 const v=value as ProcessingReport;
 if(v?.profile!=='cospace.resource-processing/0.1'||workspace&&v.workspace_id!==workspace||v.resource_id!==resource||!['ready','partial','not_applicable'].includes(v.status)||v.source_files_rechecked!==false||v.jobs_polled!==false||!Array.isArray(v.nodes)||v.nodes.length>10000||!v.nodes.every(validNode)||!Array.isArray(v.edges)||!Array.isArray(v.issues)||!v.issues.every(i=>typeof i==='string'))throw new Error('处理血缘响应无效。');
 const keys=new Set(v.nodes.map(n=>n.key));
 if(keys.size!==v.nodes.length||v.focus!==null&&!keys.has(v.focus)||v.edges.some(e=>!e||!keys.has(e.from)||e.to!==null&&!keys.has(e.to)||!relations.includes(e.relation)||!['matched','unresolved'].includes(e.status)||e.status==='matched'&&e.to===null))throw new Error('处理关系超出当前资源范围。');
 if(v.status==='ready'&&(v.focus===null||v.issues.length||v.edges.some(e=>e.status!=='matched'))||v.status==='not_applicable'&&(v.nodes.length||v.edges.length||v.focus!==null))throw new Error('处理证据状态不一致。');
 return v;
}
export function parseGovernance(value:unknown,workspace:string,resource:string):GovernanceReport{
 const v=value as GovernanceReport;
 if(v?.profile!=='cospace.resource-governance/0.1'||workspace&&v.workspace_id!==workspace||v.resource_id!==resource||!['active','archived'].includes(v.state)||!count(v.revision)||!digest(v.snapshot)||v.physical_delete_supported!==false||v.impact?.scope!=='workspace'||![v.impact.linked_references,v.impact.active_grants].every(count)||!Array.isArray(v.actions)||v.actions.length!==2)throw new Error('归档影响响应无效。');
 const archive=v.actions.find(a=>a.action==='archive'),restore=v.actions.find(a=>a.action==='restore');
 if(!archive||!restore||archive.allowed!==(v.state==='active'&&!v.impact.linked_references&&!v.impact.active_grants)||restore.allowed!==(v.state==='archived')||v.actions.some(a=>!Array.isArray(a.blockers)||!a.blockers.every(b=>['resource_has_references','resource_has_active_grants'].includes(b))))throw new Error('归档许可与引用影响不一致。');
 if(v.last_change!==null&&(!v.last_change||typeof v.last_change.reason!=='string'||!Number.isFinite(Date.parse(v.last_change.updated_at))))throw new Error('归档操作记录无效。');
 return v;
}
export function validateGovernanceResult(value:unknown,resource:string,action:'archive'|'restore',revision:number){
 const v=value as {resource_id?:string;action?:string;after?:{resource_id?:string;state?:string;revision?:number}};
 if(v?.resource_id!==resource||v.action!==action||v.after?.resource_id!==resource||v.after.state!==(action==='archive'?'archived':'active')||v.after.revision!==revision+1)throw new Error('操作结果与当前资料不一致，请刷新核查。');
}
