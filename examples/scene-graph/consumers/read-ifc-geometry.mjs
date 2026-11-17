// Builtins-only consumer. Host supplies buffers and independently trusted pins; no file paths.
import {createHash} from 'node:crypto';
import {inspectStructure} from './read-ifc-structure.mjs';

const fields=['profile','source','structure_sha256','entity_id','element_id','source_mesh_sha256',
 'frame_id','unit','encoding','vertices','triangles','data_kind','assessment','alignment_verified',
 'ontology_bound','real_release_ready'];
function check(ok,message){if(!ok){throw new Error(message);}}
function compare(a,b){
 if(a<b){return -1;}
 return Number(a>b);
}
function canonical(value){
 if(value&&typeof value==='object'){
  return '{'+Object.keys(value).sort(compare).map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
 }
 return JSON.stringify(value);
}
function headerBinding(header,snapshot,expected){
 check(Object.keys(header).sort(compare).join(',')===[...fields].sort(compare).join(','),'geometry_header_fields');
 check(header.profile==='cospace.ifc-element-geometry/0.1'&&header.unit==='m'
  &&header.encoding==='float64le_xyz_uint32le_triangles','geometry_encoding');
 check(header.data_kind==='ifc_design_candidate'&&header.assessment==='unverified'
  &&header.alignment_verified===false&&header.ontology_bound===false
  &&header.real_release_ready===false,'geometry_design_only');
 check(canonical(header.source)===canonical(snapshot.source)
  &&header.structure_sha256===expected.structureSha256&&header.frame_id===snapshot.frame_id
  &&header.element_id===expected.element,'geometry_structure_binding');
 const subject=snapshot.entities.find(e=>e.element_id===expected.element);
 check(subject?.geometry_status==='extracted'&&subject.entity_id===header.entity_id,'geometry_entity_binding');
 check(typeof header.source_mesh_sha256==='string'&&/^[a-f0-9]{64}$/.test(header.source_mesh_sha256),'geometry_mesh_digest');
 check(Number.isSafeInteger(header.vertices)&&header.vertices>=1&&header.vertices<=200000
  &&Number.isSafeInteger(header.triangles)&&header.triangles>=1&&header.triangles<=400000,'geometry_count_budget');
}
function coordinates(raw,start,count){
 const vertices=new Float64Array(count*3),bounds=[[Infinity,Infinity,Infinity],[-Infinity,-Infinity,-Infinity]];
 for(let i=0;i<vertices.length;i++){
  const value=raw.readDoubleLE(start+i*8);
  check(Number.isFinite(value)&&Math.abs(value)<=10000000,'geometry_coordinates');
  vertices[i]=value;
  bounds[0][i%3]=Math.min(bounds[0][i%3],value);
  bounds[1][i%3]=Math.max(bounds[1][i%3],value);
 }
 return {vertices,bounds};
}
export function readGeometry(raw,structureRaw,expected){
 // Existing consumer validates exact structure bytes, external source pins and reference closure.
 inspectStructure(structureRaw,expected.structureSha256,expected.source);
 check(Buffer.isBuffer(raw)&&raw.length>12&&raw.length<=10*1024*1024,'geometry_byte_budget');
 check(typeof expected.sha256==='string'&&/^[a-f0-9]{64}$/.test(expected.sha256)
  &&createHash('sha256').update(raw).digest('hex')===expected.sha256,'geometry_byte_digest');
 check(raw.subarray(0,8).equals(Buffer.from('CSIFCG01','ascii')),'geometry_magic');
 const size=raw.readUInt32LE(8);
 check(size>=1&&size<=4096&&12+size<=raw.length,'geometry_header_budget');
 const metadata=raw.subarray(12,12+size),header=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(metadata));
 // Metadata contains only integer numbers and ASCII keys; duplicate keys/extra fields are rejected.
 check(Buffer.from(canonical(header),'utf8').equals(metadata),'geometry_canonical_header');
 const snapshot=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(structureRaw));
 headerBinding(header,snapshot,expected);
 const start=12+size,faceStart=start+header.vertices*24;
 check(raw.length===faceStart+header.triangles*12,'geometry_payload_length');
 const {vertices,bounds}=coordinates(raw,start,header.vertices),triangles=new Uint32Array(header.triangles*3);
 for(let i=0;i<triangles.length;i++){
  const value=raw.readUInt32LE(faceStart+i*4);
  check(value<header.vertices,'geometry_triangle_index');triangles[i]=value;
 }
 const summary={profile:header.profile,source:header.source,structure_sha256:header.structure_sha256,
  entity_id:header.entity_id,element_id:header.element_id,frame_id:header.frame_id,unit:'m',
  vertices:header.vertices,triangles:header.triangles,bounds,data_kind:'ifc_design_candidate',
  assessment:'unverified',original_ifc_content_verified:false,original_mesh_content_verified:false,
  alignment_verified:false,ontology_bound:false,real_release_ready:false};
 return {header,vertices,triangles,summary};
}
