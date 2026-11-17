export type SurfaceRequest={space_id:string;catalog_sha256:string;frame_id:string;point_xyz_m:number[];max_distance_m:number};
type Subject={entity_id:string;element_id:string;ifc_type:string;name:string;geometry_status:string};
type Hit={entity_id:string;element_id:string;ifc_type:string;name:string;distance_m:number;triangle_index:number;closest_point_xyz_m:number[];source_mesh_sha256:string};
export type SurfaceResult={status:'found'|'no_match'|'geometry_unavailable';match:Hit|null;tested_components:number;without_geometry:number};
const xyz=(v:unknown,maximum=1_000_000):v is number[]=>Array.isArray(v)&&v.length===3&&v.every(n=>typeof n==='number'&&Number.isFinite(n)&&Math.abs(n)<=maximum);
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export function checkedSurface(value:unknown,query:SurfaceRequest,subjects:Subject[]):SurfaceResult{
 const v=value as SurfaceResult&Record<string,unknown>&{
  source:{space_id:string;catalog_sha256:string;ifc_sha256:string};query:SurfaceRequest;tested_triangles:number;frame_id:string};
 const extracted=subjects.filter(s=>s.geometry_status==='extracted');
 if(v?.profile!=='cospace.ifc-nearest-surface/0.1'||v.source?.space_id!==query.space_id||v.source?.catalog_sha256!==query.catalog_sha256||
  !hash(v.source?.ifc_sha256)||v.frame_id!==query.frame_id||v.frame_id!=='ifc_world_'+v.source.ifc_sha256.slice(0,16)||v.unit!=='m'||
  v.query?.space_id!==query.space_id||v.query?.catalog_sha256!==query.catalog_sha256||v.query?.frame_id!==query.frame_id||
  !xyz(v.query?.point_xyz_m)||v.query.point_xyz_m.some((n:number,i:number)=>n!==query.point_xyz_m[i])||v.query.max_distance_m!==query.max_distance_m||
  v.data_kind!=='ifc_design_candidate'||v.assessment!=='unverified'||v.alignment_verified!==false||v.ontology_bound!==false||v.real_release_ready!==false||
  v.coverage!=='all_extracted_structure_entities'||v.method!=='unsigned_point_to_triangle_surface'||v.tie_policy!=='lowest_element_id_then_triangle_index'||
  v.tested_components!==extracted.length||v.without_geometry!==subjects.length-extracted.length||
  !Number.isSafeInteger(v.tested_triangles)||v.tested_triangles<extracted.length||v.tested_triangles>400000)throw new Error('空间查询响应不一致。');
 if(v.status==='found'){
  const h=v.match,source=extracted.find(s=>s.element_id===h?.element_id);
  if(!h||!source||source.entity_id!==h.entity_id||source.ifc_type!==h.ifc_type||source.name!==h.name||
   !xyz(h.closest_point_xyz_m,10_000_000)||!hash(h.source_mesh_sha256)||!Number.isSafeInteger(h.triangle_index)||h.triangle_index<0||h.triangle_index>=v.tested_triangles||
   typeof h.distance_m!=='number'||!Number.isFinite(h.distance_m)||h.distance_m<0||h.distance_m>query.max_distance_m||
   Math.abs(Math.hypot(...h.closest_point_xyz_m.map((n,i)=>n-query.point_xyz_m[i]))-h.distance_m)>1e-7)throw new Error('最近构件响应不一致。');
 }else if(v.match!==null||(v.status==='no_match'?extracted.length===0:v.status!=='geometry_unavailable'||extracted.length!==0)){
  throw new Error('空间查询状态不一致。');
 }
 return v;
}
