export type OntologyPin={ontology_id:string;version:string;sha256:string};
export type SourceType={entity_id:string;element_id:string;ifc_type:string};
export type TypeProposal={source_entity_id:string;element_id:string;ifc_type:string;target_type_id:string|null;status:'proposed'|'unmapped'};
export type TypeProposals={profile:string;source:{space_id:string;catalog_sha256:string};ontology_ref:OntologyPin;mapping:{profile:string;ontology_ref:OntologyPin;rules:{ifc_type:string;target_type_id:string}[]};mapping_sha256:string;structure_sha256:string;entities:TypeProposal[];proposed_count:number;unmapped_count:number};
export function checkedTypeProposals(value:unknown,space:string,pin:string,ontology:OntologyPin,sources:SourceType[],rules:Record<string,string>):TypeProposals{
 const v=value as TypeProposals&Record<string,unknown>;
 if(v?.profile!=='cospace.ifc-structure-type-proposals/0.1'||v.source?.space_id!==space||v.source.catalog_sha256!==pin||
  v.ontology_ref?.ontology_id!==ontology.ontology_id||v.ontology_ref.version!==ontology.version||v.ontology_ref.sha256!==ontology.sha256||
  !/^[a-f0-9]{64}$/.test(v.mapping_sha256)||!/^[a-f0-9]{64}$/.test(v.structure_sha256)||
  v.data_kind!=='ifc_design_candidate'||v.assessment!=='unverified'||v.instance_validated!==false||
  v.relationships_mapped!==false||v.ontology_bound!==false||v.alignment_verified!==false||v.saved!==false||v.real_release_ready!==false||
  !Array.isArray(v.entities)||v.entities.length!==sources.length)throw new Error('类型提案响应与固定来源不一致。');
 validateMapping(v.mapping,ontology,rules);
 const expected=new Map(sources.map(e=>[e.entity_id,e])),seen=new Set<string>();let count=0;
 for(const row of v.entities){
  const source=expected.get(row?.source_entity_id),target=source?rules[source.ifc_type]||null:null;
  if(!source||seen.has(row.source_entity_id)||row.element_id!==source.element_id||row.ifc_type!==source.ifc_type||
   row.target_type_id!==target||row.status!==(target?'proposed':'unmapped'))throw new Error('类型提案实体或规则不一致。');
  seen.add(row.source_entity_id);if(target)count++;
 }
 if(v.proposed_count!==count||v.unmapped_count!==sources.length-count)throw new Error('类型提案统计不一致。');
 return v;
}
function validateMapping(mapping:TypeProposals['mapping'],ontology:OntologyPin,rules:Record<string,string>){
 if(mapping?.profile!=='cospace.ifc-ontology-mapping/0.1'||mapping.ontology_ref?.ontology_id!==ontology.ontology_id||
  mapping.ontology_ref.version!==ontology.version||mapping.ontology_ref.sha256!==ontology.sha256||
  !Array.isArray(mapping.rules)||mapping.rules.length!==Object.values(rules).filter(Boolean).length)throw new Error('提案规则记录不一致。');
 const seen=new Set<string>();
 for(const row of mapping.rules){
  if(!row||seen.has(row.ifc_type)||!rules[row.ifc_type]||rules[row.ifc_type]!==row.target_type_id)throw new Error('提案规则记录不一致。');
  seen.add(row.ifc_type);
 }
}
