import type {OntologyPin,TypeProposals} from './ifc-type-proposal-contract';
import {checkedJsonFile} from './checked-json-file.ts';

export const MAX_MAPPING_FILE_BYTES=8*1024*1024;
const PROFILE='cospace.ifc-type-mapping-file/0.1';
const PROPOSALS='cospace.ifc-structure-type-proposals/0.1';
const MAPPING='cospace.ifc-ontology-mapping/0.1';
const validId=(v:unknown):v is string=>typeof v==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}$/.test(v);
const validDigest=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const object=(v:unknown):Record<string,unknown>|null=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:null;
const hasKeys=(v:Record<string,unknown>,keys:string[])=>Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));

export function readMappingFile(text:string,space:string,pin:string){
 let value:Record<string,unknown>|null;
 try{value=object(checkedJsonFile(text,MAX_MAPPING_FILE_BYTES));}catch{throw new Error('文件 JSON 无效、存在重复字段或超出大小/层级限制。');}
 if(!value||(value.profile!==PROFILE&&value.profile!==PROPOSALS))throw new Error('请选择映射配置或已导出的类型提案。');
 const source=object(value.source);
 if(source?.space_id!==space||source.catalog_sha256!==pin)throw new Error('文件与当前场景或 IFC 目录版本不一致。');
 if(value.profile===PROFILE&&(!hasKeys(value,['profile','source','mapping'])||!hasKeys(source,['space_id','catalog_sha256'])))throw new Error('映射配置格式不正确。');
 const mapping=object(value.mapping),ref=object(mapping?.ontology_ref);
 if(!mapping||!hasKeys(mapping,['profile','ontology_ref','rules'])||mapping.profile!==MAPPING||
  !ref||!hasKeys(ref,['ontology_id','version','sha256'])||!validId(ref.ontology_id)||!validId(ref.version)||!validDigest(ref.sha256)||
  !Array.isArray(mapping.rules)||mapping.rules.length<1||mapping.rules.length>100)throw new Error('文件的固定本体或类型规则不完整。');
 const rules=new Map<string,string>();
 for(const entry of mapping.rules){
  const row=object(entry);
  if(!row||!hasKeys(row,['ifc_type','target_type_id'])||typeof row.ifc_type!=='string'||!/^Ifc[A-Za-z0-9]{1,100}$/.test(row.ifc_type)||
   rules.has(row.ifc_type)||!validId(row.target_type_id))throw new Error('文件存在重复或无效的 IFC 类型规则。');
  rules.set(row.ifc_type,row.target_type_id);
 }
 return {ontology:{ontology_id:ref.ontology_id,version:ref.version,sha256:ref.sha256},rules:Object.fromEntries(rules)};
}

export function mappingDocument(ontology:OntologyPin,rules:Record<string,string>):TypeProposals['mapping']{
 const {ontology_id,version,sha256}=ontology;
 const rows=Object.entries(rules).filter(([,target])=>target);
 return {profile:MAPPING,ontology_ref:{ontology_id,version,sha256},rules:rows.map(([ifc_type,target_type_id])=>({ifc_type,target_type_id}))};
}

export function mappingFile(space:string,pin:string,ontology:OntologyPin,rules:Record<string,string>){
 return {profile:PROFILE,source:{space_id:space,catalog_sha256:pin},mapping:mappingDocument(ontology,rules)};
}

export function validateMappingTargets(rules:Record<string,string>,types:Record<string,unknown>){
 if(Object.values(rules).some(target=>!Object.hasOwn(types,target)))throw new Error('文件引用了该本体版本中没有的目标类型。');
}
