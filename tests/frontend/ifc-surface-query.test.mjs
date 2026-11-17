import assert from 'node:assert/strict';
import test from 'node:test';
import {checkedSurface} from '../../apps/workbench/src/layout/ifc-surface-contract.ts';
const query={space_id:'space-1111111111111111',catalog_sha256:'a'.repeat(64),frame_id:'ifc_world_'+'b'.repeat(16),point_xyz_m:[.5,.5,2],max_distance_m:3};
const subjects=[{entity_id:'wall',element_id:'e00001',ifc_type:'IfcWall',name:'wall',geometry_status:'extracted'}];
function sample(){return {profile:'cospace.ifc-nearest-surface/0.1',source:{space_id:query.space_id,catalog_sha256:query.catalog_sha256,ifc_sha256:'b'.repeat(64)},
 frame_id:query.frame_id,unit:'m',query:{...query},status:'found',tested_components:1,tested_triangles:4,without_geometry:0,
 coverage:'all_extracted_structure_entities',method:'unsigned_point_to_triangle_surface',tie_policy:'lowest_element_id_then_triangle_index',
 data_kind:'ifc_design_candidate',assessment:'unverified',alignment_verified:false,ontology_bound:false,real_release_ready:false,
 match:{entity_id:'wall',element_id:'e00001',ifc_type:'IfcWall',name:'wall',distance_m:2,closest_point_xyz_m:[.5,.5,0],triangle_index:0,source_mesh_sha256:'c'.repeat(64)}};}
const check=v=>checkedSurface(v,query,subjects);
test('fixed source point and closest surface response accepted',()=>{
 assert.equal(check(sample()).match.distance_m,2);
 assert.equal(check({...sample(),status:'no_match',match:null}).match,null);
 const empty={...sample(),status:'geometry_unavailable',match:null,tested_components:0,tested_triangles:0,without_geometry:1};
 assert.equal(checkedSurface(empty,query,[{...subjects[0],geometry_status:'no_representation'}]).status,'geometry_unavailable');
});
test('source frame query promotion coverage and contradictory statuses rejected',()=>{
 for(const change of [{source:{}},{frame_id:'other'},{query:{...query,max_distance_m:4}},
  {query:{...query,point_xyz_m:[1,1,1]}},{alignment_verified:true},{ontology_bound:true},{real_release_ready:true},
  {tested_components:0},{tested_triangles:400001},{without_geometry:2},{status:'no_match'},{status:'geometry_unavailable',match:null}])assert.throws(()=>check({...sample(),...change}));
});
test('unknown entity distance coordinates triangle and radius inconsistencies rejected',()=>{
 for(const change of [{element_id:'e00002'},{entity_id:'other'},{ifc_type:'IfcDoor'},{distance_m:3.1},
  {distance_m:1},{distance_m:Number.NaN},{triangle_index:-1},{triangle_index:4},{closest_point_xyz_m:[0,0]},
  {closest_point_xyz_m:[1,1,1]},{source_mesh_sha256:'bad'}])assert.throws(()=>check({...sample(),match:{...sample().match,...change}}));
});
