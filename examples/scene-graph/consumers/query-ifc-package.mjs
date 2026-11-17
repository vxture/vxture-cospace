// Offline host supplies package bytes and independent pins. No service or Python runtime.
import {readPackage} from './read-ifc-package.mjs';
import {readGeometry} from './read-ifc-geometry.mjs';

function check(ok,message){if(!ok){throw new Error(message);}}
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
const dot=(a,b)=>a.reduce((sum,v,i)=>sum+v*b[i],0);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const distance2=(a,b)=>dot(sub(a,b),sub(a,b));
function triangleSurface(point,a,b,c){
 let nearest=a,minimum=distance2(point,a);
 const edges=[[a,b],[b,c],[c,a]];
 for(const [u,v] of edges){
  const edge=sub(v,u),length=dot(edge,edge);
  const fraction=length>0?Math.max(0,Math.min(1,dot(sub(point,u),edge)/length)):0;
  const candidate=u.map((x,i)=>x+fraction*edge[i]),d2=distance2(point,candidate);
  if(d2<minimum){nearest=candidate;minimum=d2;}
 }
 const normal=cross(sub(b,a),sub(c,a)),norm2=dot(normal,normal);
 if(norm2>0){
  const offset=dot(sub(point,a),normal)/norm2;
  const projection=point.map((v,i)=>v-offset*normal[i]);
  const inside=edges.every(([u,v])=>dot(cross(sub(v,u),sub(projection,u)),normal)>=0);
  const d2=distance2(point,projection);
  if(inside&&d2<minimum){nearest=projection;minimum=d2;}
 }
 return {squared:minimum,closest_point_xyz_m:nearest};
}
function nearestMesh(point,vertices,triangles){
 let best=null;
 for(let i=0;i<triangles.length;i+=3){
  const points=[0,1,2].map(j=>{
   const start=triangles[i+j]*3;
   return Array.from(vertices.subarray(start,start+3));
  });
  const hit=triangleSurface(point,...points);
  if(best===null||hit.squared<best.squared){best={...hit,triangle_index:i/3};}
 }
 return {distance_m:Math.sqrt(best.squared),triangle_index:best.triangle_index,
  closest_point_xyz_m:best.closest_point_xyz_m};
}
function validateQuery(query){
 check(query&&typeof query==='object'&&!Array.isArray(query)
  &&Object.keys(query).sort().join(',')==='frame_id,max_distance_m,point_xyz_m','offline_surface_query_fields');
 check(typeof query.frame_id==='string'&&/^ifc_world_[a-f0-9]{16}$/.test(query.frame_id),'offline_surface_frame');
 check(Array.isArray(query.point_xyz_m)&&query.point_xyz_m.length===3
  &&query.point_xyz_m.every(v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=1000000),'offline_surface_point');
 check(typeof query.max_distance_m==='number'&&Number.isFinite(query.max_distance_m)
  &&query.max_distance_m>0&&query.max_distance_m<=1000,'offline_surface_radius');
}
export function queryPackageSurface(raw,expected,query){
 validateQuery(query);
 const loaded=readPackage(raw,expected),{manifest,structure,members,summary}=loaded;
 check(query.frame_id===structure.frame_id,'offline_surface_frame_mismatch');
 check(summary.triangles<=400000,'offline_surface_triangle_budget');
 const entities=new Map(structure.entities.map(e=>[e.element_id,e]));
 let best=null;
 for(const member of manifest.members.slice(1)){
  const element=member.name.slice(0,-4),entity=entities.get(element);
  const geometry=readGeometry(members.get(member.name),members.get('structure.json'),{
   sha256:member.sha256,structureSha256:manifest.structure_sha256,source:expected.source,element});
  const hit=nearestMesh(query.point_xyz_m,geometry.vertices,geometry.triangles);
  if(best===null||hit.distance_m<best.distance_m){
   best={...hit,entity_id:entity.entity_id,element_id:element,ifc_type:entity.ifc_type,name:entity.name,
    source_mesh_sha256:geometry.header.source_mesh_sha256,geometry_component_sha256:member.sha256};
  }
 }
 const match=best!==null&&best.distance_m<=query.max_distance_m?best:null;
 let status=match?'found':'no_match';
 if(summary.geometry_components===0){status='geometry_unavailable';}
 return {profile:'cospace.ifc-offline-nearest-surface/0.1',source:manifest.source,
  package_sha256:expected.sha256,structure_sha256:manifest.structure_sha256,
  frame_id:structure.frame_id,unit:'m',query,status,match,
  tested_components:summary.geometry_components,tested_triangles:summary.triangles,
  without_geometry:summary.without_geometry,coverage:'all_extracted_structure_entities',
  method:'unsigned_point_to_triangle_surface',tie_policy:'lowest_element_id_then_triangle_index',
  data_kind:'ifc_design_candidate',assessment:'unverified',original_ifc_content_verified:false,
  original_mesh_content_verified:false,alignment_verified:false,ontology_bound:false,real_release_ready:false,
  limitations:['selected_ifc_classes_only','missing_geometry_not_searched','no_room_containment',
   'no_inside_outside_or_collision_test','no_field_alignment_or_current_state','no_navigation_or_traversability']};
}
