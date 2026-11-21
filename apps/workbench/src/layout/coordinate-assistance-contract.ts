export type AxisProposal={direction:string|null;evidence_quote:string};
export type CoordinateSuggestion={profile:string;space_id:string;input_id:string|null;expected_revision:number|null;task_id:string;evidence_sha256:string;proposal:{axes:AxisProposal[];unit:string|null;unit_evidence_quote:string;unresolved:string[]};can_apply_axes:boolean;requires_confirmation:boolean;coordinate_transform_applied:boolean};
const directions=new Set(['right','left','forward','backward','up','down','east','west','north','south']);
export function validateCoordinateSuggestion(value:CoordinateSuggestion,context:{space:string;input:string|null;revision:number|null;task:string;sha256:string;evidence:string}){
 if(value?.profile!=='cospace.coordinate-assistance/0.1'||value.space_id!==context.space||value.input_id!==context.input||value.expected_revision!==context.revision||value.task_id!==context.task||value.evidence_sha256!==context.sha256||value.requires_confirmation!==true||value.coordinate_transform_applied!==false)throw Error('解析建议与本次资料不一致，请重新解析。');
 const proposal=value.proposal;
 if(!proposal||!Array.isArray(proposal.axes)||proposal.axes.length!==3||proposal.axes.some(a=>!a||a.direction!==null&&!directions.has(a.direction)||typeof a.evidence_quote!=='string'||a.evidence_quote.length>100||a.direction!==null&&(!a.evidence_quote.trim()||!context.evidence.includes(a.evidence_quote)))||!['m','cm','mm',null].includes(proposal.unit)||typeof proposal.unit_evidence_quote!=='string'||proposal.unit!==null&&(!proposal.unit_evidence_quote.trim()||!context.evidence.includes(proposal.unit_evidence_quote))||!Array.isArray(proposal.unresolved)||proposal.unresolved.length>6||proposal.unresolved.some(v=>typeof v!=='string'||v.length>240)||typeof value.can_apply_axes!=='boolean')throw Error('解析建议缺少有效依据，请核对来源后重试。');
 if(value.can_apply_axes&&(proposal.axes.some(a=>!a.direction)||proposal.unit!=='m'||proposal.unresolved.length))throw Error('解析建议仍需补充或转换，不能直接填入。');
 return value;
}
export function suggestionReason(value:CoordinateSuggestion){
 return [`Atlas任务 ${value.task_id}`, ...value.proposal.axes.map((axis,i)=>`${'XYZ'[i]}：${axis.evidence_quote.slice(0,80)}`),...(value.proposal.unit_evidence_quote?[`单位：${value.proposal.unit_evidence_quote.slice(0,80)}`]:[])].join('；').slice(0,500);
}
