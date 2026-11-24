import {validUse,type ResourceUse} from './data-sharing-contract.ts';
import type {DataVersion} from './data-catalog-contract';

export type TraceVersion=DataVersion&{recorded_at:string|null;current:boolean|null;snapshot_saved:boolean};
export type ResourceTrace={profile:'cospace.resource-lineage/0.1';workspace_id:string;resource_id:string;project_id:string|null;view:'source'|'reference';resource:{label:string;kind:string|null;owner:string};source:{state:'current'|'unavailable'|'restricted';version_id:string|null;space_name:string|null;href:string|null};versions:TraceVersion[];references:ResourceUse[];summary:{linked_references:number;effective_references:number;historical_references:number;projects:number;scope:'visible_only'};impact:{scope:'visible_only';retention_required:boolean;global_assessment:'not_assessed';physical_delete_supported:false};total:number;offset:number;limit:number;next_offset:number|null;status:'ready'|'partial';source_files_rechecked:false};
const digest=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const count=(v:unknown)=>Number.isInteger(v)&&Number(v)>=0;
function validVersion(v:TraceVersion,view:string){
 if(!v||!digest(v.version_id)||v.reference_kind!=='source_metadata'||typeof v.snapshot_saved!=='boolean')return false;
 if(view==='reference')return v.current===null&&v.recorded_at===null&&v.snapshot_saved;
 return (v.current===null||typeof v.current==='boolean')&&typeof v.recorded_at==='string';
}
function validSource(s:ResourceTrace['source'],view:string){
 if(!s)return false;
 if(view==='reference')return s.state==='restricted'&&s.href===null&&s.space_name===null&&s.version_id===null;
 if(!['current','unavailable'].includes(s.state)||s.version_id!==null&&!digest(s.version_id))return false;
 return s.href===null||typeof s.href==='string'&&/^#(?:data|build)\?/.test(s.href);
}
function validSummary(v:ResourceTrace){
 const s=v.summary;
 return !!s&&s.scope==='visible_only'&&[s.linked_references,s.effective_references,s.historical_references,s.projects].every(count)&&s.effective_references<=s.linked_references&&s.linked_references+s.historical_references===v.total;
}
function validImpact(v:ResourceTrace){
 const i=v.impact;
 return !!i&&i.scope==='visible_only'&&i.global_assessment==='not_assessed'&&i.physical_delete_supported===false&&i.retention_required===(v.summary.linked_references>0);
}
function validReferences(v:ResourceTrace,resource:string,project?:string){
 const versions=new Set(v.versions.map(version=>version.version_id));
 return v.references.every(u=>validUse(u)&&u.resource_id===resource&&(!project||u.project_id===project)&&versions.has(u.version_id));
}
export function parseResourceTrace(value:unknown,scope:{workspace:string;resource:string;project?:string;offset:number}):ResourceTrace{
 const v=value as ResourceTrace,view=scope.project?'reference':'source';
 if(v?.profile!=='cospace.resource-lineage/0.1'||scope.workspace&&v.workspace_id!==scope.workspace||v.resource_id!==scope.resource||(v.project_id||'')!==(scope.project||'')||v.view!==view||v.offset!==scope.offset||!count(v.total)||!Array.isArray(v.versions)||!Array.isArray(v.references)||!['ready','partial'].includes(v.status)||v.source_files_rechecked!==false)throw new Error('追溯结果与当前资源不一致。');
 if(!v.resource||typeof v.resource.label!=='string'||typeof v.resource.owner!=='string'||!validSource(v.source,view)||!v.versions.every(x=>validVersion(x,view)))throw new Error('来源或版本记录无效。');
 if(!validReferences(v,scope.resource,scope.project)||v.next_offset!==null&&(!count(v.next_offset)||v.next_offset<=v.offset))throw new Error('引用范围无效。');
 if(!validSummary(v)||!validImpact(v))throw new Error('影响统计范围无效。');
 return v;
}
