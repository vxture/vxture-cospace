type Entity={entity_id:string;element_id:string;name:string;ifc_type:string;source_role:string;geometry_status:string};
type Relation={ifc_relation_id:string;kind:string;source_id:string;target_id:string};
export type Structure={entities:Entity[];relations:Relation[];declared_role_counts:Record<string,number>;structure_available:boolean};
export const relations:Record<string,string>={aggregates:'组成',contained_in:'声明归属',opening_in:'开洞于',fills:'填充',space_boundary:'边界声明'};

export function checked(value:unknown,space:string,pin:string):Structure {
 const v=value as Structure&Record<string,unknown>;
 if(!v||v.profile!=='cospace.ifc-structure-view/0.1'||v.space_id!==space||v.catalog_sha256!==pin||
  v.configured!==true||v.data_kind!=='ifc_design_candidate'||v.assessment!=='unverified'||v.unit!=='m'||
  v.alignment_verified!==false||v.ontology_bound!==false||v.real_release_ready!==false||
  v.geometry_integrity_checked!==false||!Array.isArray(v.confirmed_connections)||v.confirmed_connections.length||
  typeof v.structure_available!=='boolean'||!Array.isArray(v.entities)||v.entities.length>10000||
  !Array.isArray(v.relations)||v.relations.length>20000||!v.declared_role_counts)throw Error('结构声明响应不一致。');
 validateEntities(v.entities);
 validateRelations(v.relations,new Set(v.entities.map(e=>e.entity_id)));
 validateCounts(v.declared_role_counts,v.entities);
 return v;
}

function validateEntities(entities:Entity[]){
 const ids=new Set<string>();
 for(const e of entities){
  if(!e||typeof e.entity_id!=='string'||!e.entity_id||e.entity_id.length>255||ids.has(e.entity_id)||
   typeof e.name!=='string'||typeof e.ifc_type!=='string'||typeof e.source_role!=='string'||
   !/^e\d{5}$/.test(e.element_id)||!['extracted','no_representation','extraction_failed'].includes(e.geometry_status))throw Error('结构实体引用不一致。');
  ids.add(e.entity_id);
 }
}
function validateRelations(edges:Relation[],ids:Set<string>){
 for(const r of edges)if(!r||typeof r.ifc_relation_id!=='string'||!Object.hasOwn(relations,r.kind)||!ids.has(r.source_id)||!ids.has(r.target_id))throw Error('结构关系引用不一致。');
}
function validateCounts(counts:Record<string,number>,entities:Entity[]){
 if(typeof counts!=='object'||Array.isArray(counts))throw Error('结构统计不一致。');
 const actual=new Map<string,number>();
 for(const e of entities)actual.set(e.source_role,(actual.get(e.source_role)||0)+1);
 if(Object.keys(counts).length!==actual.size)throw Error('结构统计不一致。');
 for(const [role,count] of Object.entries(counts))if(!Number.isSafeInteger(count)||count<0||actual.get(role)!==count)throw Error('结构统计不一致。');
}

