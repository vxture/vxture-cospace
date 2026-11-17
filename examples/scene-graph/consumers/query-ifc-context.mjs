// Source-relation lookup over pinned declaration bytes. No geometry, routing or adoption.
import {inspectStructure} from './read-ifc-structure.mjs';

const kinds=['aggregates','contained_in','opening_in','fills','space_boundary'];
function check(ok,message){if(!ok){throw new Error(message);}}
function validateQuery(query){
 check(query&&typeof query==='object'&&!Array.isArray(query),'context_query_object');
 check(Object.keys(query).every(key=>['element_id','max_hops','relation_kinds'].includes(key)),'context_query_fields');
 check(Object.hasOwn(query,'element_id')&&typeof query.element_id==='string'
  &&/^e[0-9]{5}$/.test(query.element_id),'context_element_id');
 const maximum=Object.hasOwn(query,'max_hops')?query.max_hops:1;
 const selected=Object.hasOwn(query,'relation_kinds')?query.relation_kinds:[...kinds];
 check(Number.isInteger(maximum)&&maximum>=1&&maximum<=4,'context_hop_budget');
 check(Array.isArray(selected)&&selected.length>=1&&selected.length<=5
  &&Array.from(selected).every(kind=>kinds.includes(kind))&&new Set(selected).size===selected.length,'context_relation_kinds');
 return {element_id:query.element_id,max_hops:maximum,relation_kinds:[...selected]};
}
function addNeighbor(neighbors,identity,other){
 if(!neighbors.has(identity)){neighbors.set(identity,new Set());}
 neighbors.get(identity).add(other);
}
function neighborhood(subject,relations,maximum){
 const neighbors=new Map();
 for(const row of relations){
  addNeighbor(neighbors,row.source_id,row.target_id);
  addNeighbor(neighbors,row.target_id,row.source_id);
 }
 const distances=new Map([[subject,0]]),pending=[subject];
 for(let i=0;i<pending.length;i++){
  const identity=pending[i],distance=distances.get(identity);
  if(distance===maximum){continue;}
  for(const other of neighbors.get(identity)||[]){
   if(!distances.has(other)){
    check(distances.size<512,'context_entity_budget');
    distances.set(other,distance+1);pending.push(other);
   }
  }
 }
 const boundary=new Set([...distances.keys()].filter(identity=>
  [...(neighbors.get(identity)||[])].some(other=>!distances.has(other))));
 return {distances,boundary};
}
export function queryDeclarationContext(raw,expected,query){
 const request=validateQuery(query);
 inspectStructure(raw,expected.sha256,expected.source);
 const snapshot=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
 const subject=snapshot.entities.find(e=>e.element_id===request.element_id);
 check(subject,'context_element_unavailable');
 const relations=snapshot.relations.filter(r=>request.relation_kinds.includes(r.kind));
 const {distances,boundary}=neighborhood(subject.entity_id,relations,request.max_hops);
 const selected=relations.filter(r=>distances.has(r.source_id)&&distances.has(r.target_id));
 check(selected.length<=2048,'context_relation_budget');
 return {profile:'cospace.ifc-declaration-context/0.1',source:snapshot.source,
  structure_sha256:expected.sha256,frame_id:snapshot.frame_id,unit:'m',query:request,subject,
  entities:snapshot.entities.filter(e=>distances.has(e.entity_id)).map(e=>({...e,hop_distance:distances.get(e.entity_id)})),
  relations:selected,boundary_entity_ids:snapshot.entities.filter(e=>boundary.has(e.entity_id)).map(e=>e.entity_id),
  has_more:boundary.size>0,coverage:'selected_ifc_classes_only',
  traversal:'undirected_source_relations_original_direction_preserved',
  data_kind:'ifc_design_candidate',assessment:'unverified',original_ifc_content_verified:false,
  geometry_included:false,alignment_verified:false,ontology_bound:false,real_release_ready:false,
  limitations:['source_declarations_not_field_facts','relation_hops_not_spatial_distance',
   'no_transitive_containment_inference','no_space_connection_inference','no_navigation_or_traversability','no_current_state']};
}
