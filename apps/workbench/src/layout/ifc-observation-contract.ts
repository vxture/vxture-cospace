export const stateLabels:Record<string,string>={unavailable:'暂无报告',expired:'报告已过期',retracted:'报告已撤销',unknown:'状态未知',conflict:'报告有冲突',reported:'来源报告'};
export const valueLabels:Record<string,string>={open:'开启',closed:'关闭',partially_open:'部分开启'};
export type State={configured:boolean;status:string;value:string|null;reported_at:string|null;active_count:number};

export function checked(raw:unknown,space:string,pin:string,element:string):State{
 const v=raw as State&Record<string,unknown>;
 if(v?.profile!=='cospace.ifc-opening-observation-view/0.1'||v.space_id!==space||v.catalog_sha256!==pin||v.element_id!==element||
  v.data_kind!=='ifc_design_candidate'||v.assessment!=='unverified'||v.catalog_content_verified!==true||
  v.source_content_verified!==false||v.evidence_content_verified!==false||v.clock_quality_verified!==false||v.real_release_ready!==false||
  typeof v.configured!=='boolean'||!Object.hasOwn(stateLabels,v.status)||!Number.isSafeInteger(v.active_count)||v.active_count<0)throw new Error('观测摘要响应不一致。');
 if(v.status==='reported'?!Object.hasOwn(valueLabels,v.value||''):v.value!==null)throw new Error('观测状态响应不一致。');
 if(!v.configured&&v.status!=='unavailable')throw new Error('观测接入状态不一致。');
 if(v.reported_at!==null&&(typeof v.reported_at!=='string'||!Number.isFinite(Date.parse(v.reported_at))))throw new Error('观测时间响应不一致。');
 return v;
}
