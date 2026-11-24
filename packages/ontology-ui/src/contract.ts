// Portable view contract: no host routing, scene, identity or endpoint imports.
export type Reference={module_id:string;version:string;sha256:string};
export type Property={title:string;definition:string;data_type:'string'|'number'|'integer'|'boolean';required:boolean;unit?:string;quantity?:string;minimum?:number};
export type Concept={title:string;definition:string;parent?:string;examples:string[];counterexamples:string[];properties:Record<string,Property>};
export type Relation={title:string;definition:string;source_types:string[];target_types:string[];symmetric:boolean};
export type ModuleDefinition={profile:'vxture.ontology-module/0.1';module_id:string;version:string;title:string;description:string;layer:'core'|'domain';status:'draft';requires:Reference[];concepts:Record<string,Concept>;relations:Record<string,Relation>};
export type Entry={reference:Reference;definition:ModuleDefinition;published_at?:string};
export type Library={profile:'vxture.ontology-catalog/0.1';status:'draft';library_sha256:string;capabilities:string[];modules:Entry[]};
export type LibraryClient={load:(signal:AbortSignal)=>Promise<Library>};

const id=/^[a-z][a-z0-9_-]{0,63}$/,version=/^\d{1,4}\.\d{1,4}\.\d{1,4}$/,digest=/^[a-f0-9]{64}$/;
function object(value:unknown):Record<string,unknown>{if(!value||typeof value!=='object'||Array.isArray(value))throw Error('本体目录格式无效。');return value as Record<string,unknown>;}
function text(value:unknown,max=2000):value is string{return typeof value==='string'&&!!value.trim()&&value.length<=max;}
function list(value:unknown,max:number):unknown[]{if(!Array.isArray(value)||value.length>max)throw Error('本体目录列表无效。');return value;}
function reference(value:unknown):Reference{const v=object(value);if(typeof v.module_id!=='string'||!id.test(v.module_id)||typeof v.version!=='string'||!version.test(v.version)||typeof v.sha256!=='string'||!digest.test(v.sha256))throw Error('本体依赖引用无效。');return v as Reference;}
function strings(value:unknown,max=256){const items=list(value,max);if(!items.length||items.some(v=>!text(v)))throw Error('本体定义文本无效。');return items as string[];}
export function parseLibrary(value:unknown):Library{return decode(value,false);}
// Directory entries are independent heads. Open one with an exact reference to validate its own closure.
export function parseLibraryDirectory(value:unknown):Library{return decode(value,true);}
function decode(value:unknown,directory:boolean):Library{
 const root=object(value);
 if(root.profile!=='vxture.ontology-catalog/0.1'||root.status!=='draft'||typeof root.library_sha256!=='string'||!digest.test(root.library_sha256))throw Error('本体目录版本或状态无效。');
 const capabilities=list(root.capabilities,8);if(capabilities.some(v=>!['definition-validation','dependency-resolution','definition-export'].includes(v as string)))throw Error('本体目录包含未支持能力。');
 const entries=list(root.modules,directory?8192:32);if(!entries.length)throw Error('本体目录缺少模块。');
 const identities=new Map<string,Entry>();
 for(const raw of entries){
  const entry=object(raw),ref=reference(entry.reference),d=object(entry.definition);
  if(entry.published_at!==undefined&&(typeof entry.published_at!=='string'||!Number.isFinite(Date.parse(entry.published_at))))throw Error('本体发布日期无效。');
  if(d.profile!=='vxture.ontology-module/0.1'||d.status!=='draft'||!['core','domain'].includes(d.layer as string)||d.module_id!==ref.module_id||d.version!==ref.version||!text(d.title,160)||!text(d.description))throw Error('本体模块与固定引用不一致。');
  if(identities.has(ref.module_id))throw Error('本体模块身份重复。');
  list(d.requires,32).forEach(reference);
  const concepts=Object.entries(object(d.concepts));if(!concepts.length||concepts.length>256)throw Error('本体概念数量无效。');
  for(const [key,rawConcept] of concepts){
   const c=object(rawConcept);if(!id.test(key)||!text(c.title,160)||!text(c.definition)||c.parent!==undefined&&!text(c.parent,129))throw Error('本体概念无效。');
   strings(c.examples,8);strings(c.counterexamples,8);
   const props=Object.entries(object(c.properties));if(props.length>32)throw Error('本体属性数量无效。');
   for(const [name,rawProp] of props){const p=object(rawProp);if(!id.test(name)||!text(p.title,160)||!text(p.definition)||!['string','number','integer','boolean'].includes(p.data_type as string)||typeof p.required!=='boolean')throw Error('本体属性无效。');
    if(p.unit!==undefined||p.quantity!==undefined){if(!text(p.unit,40)||!text(p.quantity,80)||!['number','integer'].includes(p.data_type as string))throw Error('本体单位无效。');}
    if(p.minimum!==undefined&&(typeof p.minimum!=='number'||!Number.isFinite(p.minimum)||!['number','integer'].includes(p.data_type as string)))throw Error('本体数值约束无效。');
   }
  }
  const relations=Object.entries(object(d.relations));if(relations.length>256)throw Error('本体关系数量无效。');
  for(const [key,rawRelation] of relations){const r=object(rawRelation);if(!id.test(key)||!text(r.title,160)||!text(r.definition)||typeof r.symmetric!=='boolean')throw Error('本体关系无效。');const source=strings(r.source_types),target=strings(r.target_types);if(new Set(source).size!==source.length||new Set(target).size!==target.length||r.symmetric&&(source.length!==target.length||source.some(v=>!target.includes(v))))throw Error('关系端点无效。');}
  identities.set(ref.module_id,entry as Entry);
 }
 if(directory)return structuredClone(root) as Library;
 const closures=new Map<string,Set<string>>();
 function closure(identity:string,visiting:Set<string>):Set<string>{
  if(visiting.has(identity))throw Error('本体依赖存在循环。');if(closures.has(identity))return closures.get(identity)!;
  visiting.add(identity);const entry=identities.get(identity)!,result=new Set([identity]),seen=new Set<string>();
  for(const dependency of entry.definition.requires){const target=identities.get(dependency.module_id);
   if(seen.has(dependency.module_id)||!target||target.reference.version!==dependency.version||target.reference.sha256!==dependency.sha256||entry.definition.layer==='core'&&target.definition.layer!=='core')throw Error('本体依赖缺失或不一致。');
   seen.add(dependency.module_id);for(const key of closure(dependency.module_id,visiting))result.add(key);
  }
  visiting.delete(identity);closures.set(identity,result);return result;
 }
 for(const identity of identities.keys())closure(identity,new Set());
 function concept(ref:string,owner:string):Concept{const [moduleId,key,...extra]=ref.split(':'),c=identities.get(moduleId)?.definition.concepts[key];if(extra.length||!c||!closures.get(owner)!.has(moduleId))throw Error('本体概念引用无法解析。');return c;}
 for(const [identity,entry] of identities){
  for(const [key,c] of Object.entries(entry.definition.concepts)){
   const seen=new Set<string>(),properties=new Set<string>();let ref:string|undefined=`${identity}:${key}`;
   while(ref){if(seen.has(ref))throw Error('本体继承存在循环。');seen.add(ref);const t=concept(ref,identity);for(const prop of Object.keys(t.properties)){if(properties.has(prop))throw Error('尚不支持覆盖继承属性。');properties.add(prop);}ref=t.parent;}
  }
  for(const r of Object.values(entry.definition.relations))for(const ref of [...r.source_types,...r.target_types])concept(ref,identity);
 }
 return structuredClone(root) as Library;
}

export function matchingModules(library:Library,layer:string,query:string):Entry[]{
 const q=query.trim().toLocaleLowerCase();return library.modules.filter(({definition:d})=>(!layer||d.layer===layer)&&(!q||[d.module_id,d.title,d.description,...Object.entries(d.concepts).flatMap(([id,c])=>[id,c.title,c.definition,...Object.values(c.properties).flatMap(p=>[p.title,p.definition])]),...Object.entries(d.relations).flatMap(([id,r])=>[id,r.title,r.definition])].some(value=>value.toLocaleLowerCase().includes(q))));
}

export function exportLibrary(library:Library,moduleId?:string){
 const checked=parseLibrary(library),wanted=new Set<string>();
 const add=(id:string)=>{if(wanted.has(id))return;const entry=checked.modules.find(v=>v.reference.module_id===id);if(!entry)throw Error('本体模块不存在。');wanted.add(id);entry.definition.requires.forEach(r=>add(r.module_id));};
 if(moduleId)add(moduleId);else checked.modules.forEach(v=>add(v.reference.module_id));
 return {profile:'vxture.ontology-library/0.1',modules:checked.modules.filter(v=>wanted.has(v.reference.module_id)).map(v=>v.definition).sort((a,b)=>a.module_id.localeCompare(b.module_id))};
}
