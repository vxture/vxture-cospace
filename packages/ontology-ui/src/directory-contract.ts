import type {Library,Reference} from './contract';

export type DirectoryGroup={group_id:string;name:string;status:'active'|'inactive'};
export type ResourceSummary={reference:Reference;title:string;description:string;layer:'core'|'domain';status:'draft';published_at?:string|null;concept_count:number;relation_count:number;revision:number;group_ids:string[]};
export type DirectoryPage={profile:'vxture.ontology-directory/0.1';snapshot:string;page:number;page_size:number;total:number;can_group:boolean;items:ResourceSummary[];groups:DirectoryGroup[]};
export type DirectoryQuery={layer:string;q:string;group:string;sort:string;page:string;page_size:string;snapshot?:string};
export type MembershipChange={request_id:string;module_id:string;expected_revision:number;group_ids:string[]};
export type DirectoryClient={list:(query:DirectoryQuery,signal:AbortSignal)=>Promise<DirectoryPage>;definition:(reference:Reference,signal:AbortSignal)=>Promise<Library>;assign:(change:MembershipChange,signal:AbortSignal)=>Promise<unknown>};

export function parseDirectory(value:unknown):DirectoryPage{
 const v=value as DirectoryPage;
 if(!v||v.profile!=='vxture.ontology-directory/0.1'||!/^[a-f0-9]{64}$/.test(v.snapshot)||!Number.isInteger(v.page)||v.page<1||!Number.isInteger(v.page_size)||v.page_size<1||v.page_size>50||!Number.isInteger(v.total)||v.total<0||typeof v.can_group!=='boolean'||!Array.isArray(v.items)||v.items.length>v.page_size||!Array.isArray(v.groups))throw Error('本体目录响应无效。');
 const ids=new Set<string>();
 for(const g of v.groups){if(!g||typeof g.group_id!=='string'||typeof g.name!=='string'||!g.name||!['active','inactive'].includes(g.status)||ids.has(g.group_id))throw Error('分组响应无效。');ids.add(g.group_id);}
 const modules=new Set<string>();
 for(const i of v.items){if(!i||!i.reference||typeof i.reference.module_id!=='string'||modules.has(i.reference.module_id)||!/^[a-f0-9]{64}$/.test(i.reference.sha256)||typeof i.reference.version!=='string'||typeof i.title!=='string'||typeof i.description!=='string'||!['core','domain'].includes(i.layer)||i.status!=='draft'||!Number.isInteger(i.revision)||i.revision<0||!Number.isInteger(i.concept_count)||i.concept_count<0||!Number.isInteger(i.relation_count)||i.relation_count<0||!Array.isArray(i.group_ids)||new Set(i.group_ids).size!==i.group_ids.length||i.group_ids.some(id=>!ids.has(id)))throw Error('本体摘要响应无效。');modules.add(i.reference.module_id);}
 return v;
}
