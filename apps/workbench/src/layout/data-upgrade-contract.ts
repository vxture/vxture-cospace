import type {ResourceItem} from './data-catalog-contract';
import {validGrant,validSnapshot,validUse,type ResourceUse,type AvailableResource,type SharedSnapshot} from './data-sharing-contract.ts';

export function fileAppendQuery(item:ResourceItem,name:string,reason:string,requestId:string){
 return new URLSearchParams({resource_id:item.resource_id!,expected_revision:String(item.revision),expected_version:item.source_version!.version_id,name,reason,request_id:requestId});
}
export type UpgradeReport={profile:'cospace.reference-upgrade/0.1';workspace_id:string;use:ResourceUse;current:SharedSnapshot;candidates:AvailableResource[];total:number;offset:number;limit:number;next_offset:number|null};
function matchingUse(v:UpgradeReport,use:ResourceUse){
 return !!v.use&&v.use.id===use.id&&v.use.resource_id===use.resource_id&&v.use.project_id===use.project_id&&v.use.space_id===use.space_id&&v.use.status==='active'&&validSnapshot(v.current)&&validUse({...v.use,snapshot:v.current,access_status:'active',allow_download:false});
}
function validPage(v:UpgradeReport,offset:number){
 return v.offset===offset&&v.limit===20&&Array.isArray(v.candidates)&&v.candidates.length<=20&&Number.isInteger(v.total)&&v.total>=v.candidates.length&&v.next_offset===(offset+20<v.total?offset+20:null);
}
function authorizedCandidate(row:AvailableResource,v:UpgradeReport){
 return !!row&&validGrant(row.grant)&&row.grant.status==='active'&&row.grant.resource_id===v.use.resource_id&&row.grant.version_id!==v.use.version_id&&(row.grant.target_kind==='workspace'||row.grant.target_project_id===v.use.project_id)&&validSnapshot(row.snapshot)&&row.snapshot.source_version.version_id===row.grant.version_id;
}
export function parseUpgradeReport(value:unknown,use:ResourceUse,workspace:string,offset:number):UpgradeReport{
 const v=value as UpgradeReport;
 if(v?.profile!=='cospace.reference-upgrade/0.1'||workspace&&v.workspace_id!==workspace||!matchingUse(v,use)||!validPage(v,offset))throw new Error('版本比较响应与当前引用不一致。');
 for(const row of v.candidates){
  if(!authorizedCandidate(row,v))throw new Error('候选版本授权无效。');
 }
 return v;
}
export function versionComparison(current:SharedSnapshot,next:SharedSnapshot){
 const date=(value:string|null)=>value?new Date(value).toLocaleString('zh-CN'):'未记录';
 const bytes=(value:number|null|undefined)=>value==null?'未记录':`${value.toLocaleString()} B`;
 return [
  ['名称',current.label,next.label],['格式',current.source_version.format||'未记录',next.source_version.format||'未记录'],
  ['大小',bytes(current.source_version.bytes),bytes(next.source_version.bytes)],
  ['形成时间',date(current.source_version.created_at),date(next.source_version.created_at)],
  ['版本',current.source_version.version_id.slice(0,12),next.source_version.version_id.slice(0,12)],
 ];
}
