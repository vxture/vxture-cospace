// Independent consumer of canonical IFC declaration snapshots. No Python or npm dependencies.
import {open} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const profile='cospace.ifc-structure-snapshot/0.1';
const roleSet=new Set(['building','level','space','door','stair','stair_flight','opening','wall','slab','distribution_board']);
const kindSet=new Set(['aggregates','contained_in','opening_in','fills','space_boundary']);
const geometrySet=new Set(['extracted','no_representation','extraction_failed']);
function requireThat(ok,message){if(!ok)throw new Error(message);}
function keys(value,expected){requireThat(value&&typeof value==='object'&&!Array.isArray(value),'object_required');requireThat(Object.keys(value).sort().join(',')===[...expected].sort().join(','),'unexpected_fields');}
function string(value,maximum,minimum=1){requireThat(typeof value==='string'&&[...value].length>=minimum&&[...value].length<=maximum,'string_budget');}
function array(value,maximum,minimum=0){requireThat(Array.isArray(value)&&value.length>=minimum&&value.length<=maximum,'array_budget');return value;}
function digest(value){requireThat(typeof value==='string'&&/^[a-f0-9]{64}$/.test(value),'digest_required');}
function canonical(value){
 if(Array.isArray(value))return `[${value.map(canonical).join(',')}]`;
 if(value&&typeof value==='object')return `{${Object.keys(value).sort().map(k=>`${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
 return JSON.stringify(value);
}
function source(value){
 keys(value,['space_id','catalog_sha256','ifc_sha256','ifc_bytes']);
 requireThat(typeof value.space_id==='string'&&/^space-[a-f0-9]{16}$/.test(value.space_id),'scene_id_required');
 digest(value.catalog_sha256);digest(value.ifc_sha256);
 requireThat(Number.isSafeInteger(value.ifc_bytes)&&value.ifc_bytes>0&&value.ifc_bytes<=128*1024*1024,'source_byte_budget');
 return canonical(value);
}
function declarations(rows){
 const ids=new Set(),elements=new Set(),counts=new Map();
 for(const row of array(rows,10000,1)){
  keys(row,['entity_id','element_id','ifc_type','source_role','name','geometry_status']);
  string(row.entity_id,255);string(row.ifc_type,110);string(row.name,4096,0);
  requireThat(/^e[0-9]{5}$/.test(row.element_id)&&typeof row.element_id==='string','element_id_required');
  requireThat(/^Ifc[A-Za-z0-9]+$/.test(row.ifc_type)&&roleSet.has(row.source_role)&&geometrySet.has(row.geometry_status),'declaration_type');
  requireThat(!ids.has(row.entity_id)&&!elements.has(row.element_id),'duplicate_entity');
  ids.add(row.entity_id);elements.add(row.element_id);counts.set(row.source_role,(counts.get(row.source_role)||0)+1);
 }
 return {ids,counts};
}
function references(rows,ids){
 const seen=new Set();
 for(const row of array(rows,20000)){
  keys(row,['ifc_relation_id','kind','source_id','target_id']);
  string(row.ifc_relation_id,255);string(row.source_id,255);string(row.target_id,255);
  requireThat(kindSet.has(row.kind)&&ids.has(row.source_id)&&ids.has(row.target_id)&&row.source_id!==row.target_id,'relation_binding');
  const key=canonical(row);requireThat(!seen.has(key),'duplicate_relation');seen.add(key);
 }
}
export function inspectStructure(raw,expectedSha256,expectedSource){
 digest(expectedSha256);
 requireThat(Buffer.isBuffer(raw)&&raw.length>0&&raw.length<=8*1024*1024,'snapshot_byte_budget');
 requireThat(createHash('sha256').update(raw).digest('hex')===expectedSha256,'snapshot_byte_digest');
 const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
 keys(value,['profile','data_kind','assessment','source','frame_id','unit','coverage','geometry_included',
  'alignment_verified','ontology_bound','real_release_ready','entities','relations']);
 requireThat(value.profile===profile&&value.data_kind==='ifc_design_candidate'&&value.assessment==='unverified','design_declarations_only');
 requireThat(source(value.source)===source(expectedSource),'source_binding');
 requireThat(value.frame_id===`ifc_world_${value.source.ifc_sha256.slice(0,16)}`&&value.unit==='m','frame_binding');
 requireThat(value.coverage==='selected_ifc_classes_only'&&value.geometry_included===false&&value.alignment_verified===false&&value.ontology_bound===false&&value.real_release_ready===false,'unverified_limits');
 const {ids,counts}=declarations(value.entities);references(value.relations,ids);
 // Export has only integer numeric fields and ASCII schema keys. Exact canonical bytes also reject duplicate JSON keys.
 requireThat(Buffer.from(canonical(value),'utf8').equals(raw),'canonical_bytes_required');
 return {profile,source:value.source,entities:value.entities.length,relations:value.relations.length,
  declared_role_counts:Object.fromEntries([...counts].sort(([a],[b])=>a.localeCompare(b))),
  data_kind:value.data_kind,assessment:value.assessment,original_ifc_content_verified:false,ontology_bound:false,
  geometry_included:false,alignment_verified:false,real_release_ready:false};
}
async function boundedFile(path,maximum){
 const file=await open(path,'r');
 try{
  const stat=await file.stat();requireThat(stat.isFile()&&stat.size<=maximum,'file_byte_budget');
  const raw=Buffer.alloc(maximum+1);let offset=0;
  while(offset<=maximum){const part=await file.read(raw,offset,raw.length-offset,null);if(!part.bytesRead)break;offset+=part.bytesRead;}
  requireThat(offset<=maximum,'file_byte_budget');return raw.subarray(0,offset);
 }finally{await file.close();}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  requireThat(process.argv.length===5,'usage: node read-ifc-structure.mjs <snapshot.json> <snapshot-sha256> <trusted-source.json>');
  const [raw,pin]=await Promise.all([boundedFile(process.argv[2],8*1024*1024),boundedFile(process.argv[4],2048)]);
  process.stdout.write(JSON.stringify(inspectStructure(raw,process.argv[3],JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(pin))))+'\n');
 }catch(error){process.stderr.write(`${error.message}\n`);process.exitCode=1;}
}
