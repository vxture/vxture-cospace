export type AssociationSource={id:string;space_id:string;state:string;display_code?:string;build_code?:string;created_at:string;finished_at?:string;view_parent_id?:string;base_candidate_id?:string};
export const associationViews=['overview','objects','relations','business','ifc','info'] as const;
export function associationSource(jobs:AssociationSource[],space:string,requested:string,selected:string|null){
 const available=jobs.filter(j=>j.space_id===space&&j.state==='succeeded');
 // Explicit inaccessible or failed sources must never fall back to another model.
 return {available,current:available.find(j=>j.id===(requested||selected||''))};
}
export function associationTitle(job:AssociationSource){return job.display_code||job.build_code||`历史快照 · ${job.id.slice(-8).toUpperCase()}`;}
export function associationTime(value?:string){return value?new Date(value).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'未记录';}
// Function-page navigation retains the mounted editors and their in-memory drafts.
// Every other query change remains guarded, including provenance and scene changes.
export function keepsAssociationDrafts(current:string,next:string){
 const a=new URL(current,'https://local.invalid'),b=new URL(next,'https://local.invalid');
 if(a.pathname!=='/association'||b.pathname!==a.pathname||!a.searchParams.get('space')||!a.searchParams.get('job'))return false;
 if(!associationViews.includes((b.searchParams.get('tab')||'overview') as typeof associationViews[number]))return false;
 a.searchParams.delete('tab');b.searchParams.delete('tab');a.searchParams.sort();b.searchParams.sort();
 return a.search===b.search&&a.hash===b.hash;
}
