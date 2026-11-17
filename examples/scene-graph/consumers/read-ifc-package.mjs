// Host provides buffers and independent pins. No archive extraction or filesystem access.
import {createHash} from 'node:crypto';
import {inspectStructure} from './read-ifc-structure.mjs';
import {readGeometry} from './read-ifc-geometry.mjs';
function check(ok,message){if(!ok){throw new Error(message);}}
function compare(a,b){
 if(a<b){return -1;}
 return Number(a>b);
}
function canonical(value){
 if(Array.isArray(value)){return '['+value.map(canonical).join(',')+']';}
 if(value&&typeof value==='object'){
  return '{'+Object.keys(value).sort(compare).map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
 }
 return JSON.stringify(value);
}
function keys(value,names){
 check(value&&typeof value==='object'&&!Array.isArray(value),'package_object');
 check(Object.keys(value).sort(compare).join(',')===[...names].sort(compare).join(','),'package_fields');
}
const digest=raw=>createHash('sha256').update(raw).digest('hex');
const hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
function readManifest(raw,expected){
 check(Buffer.isBuffer(raw)&&raw.length>12&&raw.length<=32*1024*1024,'package_byte_budget');
 check(hash(expected.sha256)&&digest(raw)===expected.sha256,'package_byte_digest');
 check(raw.subarray(0,8).equals(Buffer.from('CSIFCP01','ascii')),'package_magic');
 const size=raw.readUInt32LE(8);
 check(size>=1&&size<=1024*1024&&12+size<=raw.length,'package_manifest_budget');
 const metadata=raw.subarray(12,12+size),manifest=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(metadata));
 check(Buffer.from(canonical(manifest),'utf8').equals(metadata),'package_canonical_manifest');
 keys(manifest,['profile','source','structure_sha256','geometry_coverage','members','data_kind','assessment',
  'alignment_verified','ontology_bound','real_release_ready']);
 check(manifest.profile==='cospace.ifc-design-package/0.1'&&manifest.geometry_coverage==='all_extracted_structure_entities'
  &&manifest.data_kind==='ifc_design_candidate'&&manifest.assessment==='unverified'
  &&manifest.alignment_verified===false&&manifest.ontology_bound===false&&manifest.real_release_ready===false,'package_design_only');
 check(canonical(manifest.source)===canonical(expected.source)&&hash(manifest.structure_sha256),'package_source_binding');
 check(Array.isArray(manifest.members)&&manifest.members.length>=1&&manifest.members.length<=513,'package_member_budget');
 return {manifest,start:12+size};
}
function readMembers(raw,manifest,start){
 const members=new Map();
 for(const member of manifest.members){
  keys(member,['name','sha256','bytes']);
  check(typeof member.name==='string'&&/^(structure\.json|e\d{5}\.bin)$/.test(member.name)
   &&!members.has(member.name),'package_member_name');
  check(Number.isSafeInteger(member.bytes)&&member.bytes>=1&&member.bytes<=10*1024*1024
   &&start+member.bytes<=raw.length,'package_member_bytes');
  const data=raw.subarray(start,start+member.bytes);
  check(hash(member.sha256)&&digest(data)===member.sha256,'package_member_digest');
  members.set(member.name,data);start+=member.bytes;
 }
 check(start===raw.length,'package_payload_length');
 return members;
}
export function readPackage(raw,expected){
 const {manifest,start}=readManifest(raw,expected),members=readMembers(raw,manifest,start);
 const structure=members.get('structure.json');
 const summary=inspectStructure(structure,manifest.structure_sha256,expected.source);
 const snapshot=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(structure));
 const names=['structure.json',...snapshot.entities.filter(e=>e.geometry_status==='extracted').map(e=>e.element_id+'.bin').sort(compare)];
 check(manifest.members.map(m=>m.name).join(',')===names.join(','),'package_geometry_coverage');
 let vertices=0,triangles=0;
 for(const member of manifest.members.slice(1)){
  const result=readGeometry(members.get(member.name),structure,{sha256:member.sha256,
   structureSha256:manifest.structure_sha256,source:expected.source,element:member.name.slice(0,-4)});
  vertices+=result.summary.vertices;triangles+=result.summary.triangles;
 }
 const report={profile:manifest.profile,source:summary.source,structure_sha256:manifest.structure_sha256,
  entities:summary.entities,relations:summary.relations,geometry_components:manifest.members.length-1,
  without_geometry:snapshot.entities.filter(e=>e.geometry_status!=='extracted').length,
  vertices,triangles,data_kind:'ifc_design_candidate',assessment:'unverified',
  original_ifc_content_verified:false,original_mesh_content_verified:false,
  alignment_verified:false,ontology_bound:false,real_release_ready:false};
 return {manifest,structure:snapshot,members,summary:report};
}
export function inspectPackage(raw,expected){return readPackage(raw,expected).summary;}
