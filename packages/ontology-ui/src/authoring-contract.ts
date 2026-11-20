import type {ModuleDefinition,Reference} from './contract';
export type Bundle={profile:'vxture.ontology-library/0.1';modules:ModuleDefinition[]};
export type Draft={module_id:string;revision:number;bundle:Bundle;sha256:string;base_reference:Reference|null;updated_at:string;updated_by:string};
export type Review={review_id:string;revision:number;draft_sha256:string;submitted_by:string;submitted_at:string;state:'pending'|'approved'|'rejected';reason:string|null;stale:boolean;can_decide:boolean};
export type WorkbenchState={profile:'vxture.ontology-workbench/0.1';module_id:string;can_manage:boolean;draft:Draft|null;source_bundle:Bundle;releases:{reference:Reference;published_at:string}[];reviews:Review[];validation:{valid:boolean;diagnostics:{code:string;path:string}[]}|null;comparison:{changes:{path:string;change:string}[]}|null};
export type AuthoringClient={read:(moduleId:string,signal:AbortSignal)=>Promise<WorkbenchState>;change:(body:Record<string,unknown>,signal:AbortSignal)=>Promise<unknown>;definition:(reference:Reference,signal:AbortSignal)=>Promise<unknown>;review:(reviewId:string,signal:AbortSignal)=>Promise<unknown>};
export function parseWorkbench(value:unknown):WorkbenchState{
 const v=value as WorkbenchState;
 const object=(o:unknown)=>!!o&&typeof o==='object'&&!Array.isArray(o);
 const strings=(a:unknown)=>Array.isArray(a)&&a.every(s=>typeof s==='string');
 if(!v||v.profile!=='vxture.ontology-workbench/0.1'||typeof v.module_id!=='string'||!/^[a-z][a-z0-9_-]{0,63}$/.test(v.module_id)||typeof v.can_manage!=='boolean'||!Array.isArray(v.releases)||!Array.isArray(v.reviews)||v.reviews.length>50)throw Error('编制工作面数据无效。');
 function bundle(b:Bundle){if(!b||b.profile!=='vxture.ontology-library/0.1'||!Array.isArray(b.modules)||!b.modules.length||b.modules.length>32)throw Error('草稿结构无效。');
  for(const m of b.modules){if(!m||typeof m.module_id!=='string'||typeof m.title!=='string'||typeof m.version!=='string'||typeof m.description!=='string'||!object(m.concepts)||!object(m.relations)||!Array.isArray(m.requires))throw Error('草稿结构暂不受表单支持，请联系编制管理员。');
   for(const c of Object.values(m.concepts)){if(!c||typeof c.title!=='string'||typeof c.definition!=='string'||!strings(c.examples)||!strings(c.counterexamples)||!object(c.properties)||c.parent!==undefined&&typeof c.parent!=='string')throw Error('概念草稿结构无效。');for(const p of Object.values(c.properties))if(!p||typeof p.title!=='string'||typeof p.definition!=='string'||!['string','number','integer','boolean'].includes(p.data_type)||typeof p.required!=='boolean')throw Error('属性草稿结构无效。');}
   for(const r of Object.values(m.relations))if(!r||typeof r.title!=='string'||typeof r.definition!=='string'||!strings(r.source_types)||!strings(r.target_types)||typeof r.symmetric!=='boolean')throw Error('关系草稿结构无效。');}
  if(!b.modules.some(m=>m.module_id===v.module_id))throw Error('草稿缺少目标本体。');}
 bundle(v.source_bundle);if(v.draft){if(v.draft.module_id!==v.module_id||!Number.isInteger(v.draft.revision)||v.draft.revision<1)throw Error('草稿修订无效。');bundle(v.draft.bundle);}
 for(const r of v.releases)if(!r||r.reference?.module_id!==v.module_id||typeof r.reference.version!=='string'||!/^[a-f0-9]{64}$/.test(r.reference.sha256)||!Number.isFinite(Date.parse(r.published_at)))throw Error('发布记录无效。');
 for(const r of v.reviews)if(!r||!/^[a-f0-9]{32}$/.test(r.review_id)||!['pending','approved','rejected'].includes(r.state)||typeof r.stale!=='boolean'||typeof r.can_decide!=='boolean'||typeof r.submitted_by!=='string'||!Number.isInteger(r.revision))throw Error('审批记录无效。');
 return v;
}
export function bumpVersion(version:string){const [major,minor]=version.split('.').map(Number);return `${major}.${minor+1}.0`;}
export function chooseDependency(bundle:Bundle,moduleId:string,reference:Reference,dependency:Bundle):Bundle{
 const result=structuredClone(bundle),target=result.modules.find(m=>m.module_id===moduleId)!;
 if(!target.requires.some(r=>r.module_id===reference.module_id))throw Error('只能替换已声明的依赖。');
 target.requires=target.requires.map(r=>r.module_id===reference.module_id?reference:r);
 const modules=new Map(result.modules.map(m=>[m.module_id,m]));for(const m of dependency.modules)modules.set(m.module_id,structuredClone(m));modules.set(moduleId,target);
 const wanted=new Set<string>();function visit(id:string){if(wanted.has(id))return;wanted.add(id);const m=modules.get(id);if(!m)throw Error('依赖闭包不完整。');m.requires.forEach(r=>visit(r.module_id));}visit(moduleId);
 return {profile:bundle.profile,modules:[...wanted].sort().map(id=>modules.get(id)!)};
}
