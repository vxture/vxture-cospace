type Facts={dirty:boolean;hasDocument:boolean;checksPassed:boolean;synthetic:boolean;reviewStatus:string;canEdit:boolean;canReview:boolean;actor:string;authoredBy:string|null;approvedRevision:number|null;adoptedRevision:number|null;validFrom?:string;validUntil?:string};
type Action='save'|'import'|'submit'|'approve'|'adopt'|'association';
type Next={action:Action|null;label?:string;description:string};
function draftStep(facts:Facts):Next{
 if(facts.canEdit&&facts.checksPassed&&!facts.synthetic)return {action:'submit',label:'提交审核',description:'参数检查已通过，下一步提交独立审核。'};
 return {action:null,description:facts.synthetic?'合成算例仅用于演示，请录入真实配准资料。':'请修正配准资料并通过检查，再提交独立审核。'};
}
function submittedStep(facts:Facts):Next{
 if(facts.canEdit&&facts.canReview&&!!facts.actor&&facts.actor!==facts.authoredBy)return {action:'approve',label:'审核配准',description:'核实控制依据、独立检查、基准与适用范围后核准。'};
 return {action:null,description:'等待独立审核，录入者不能审核自己的资料。'};
}
function approvedStep(facts:Facts,now:number):Next{
 const valid=Number.isFinite(now)&&Date.parse(facts.validFrom||'')<=now&&now<Date.parse(facts.validUntil||'');
 if(!valid)return {action:null,description:'核准修订不在有效期内，请核对有效期并更新审核依据。'};
 if(facts.approvedRevision!==null&&facts.adoptedRevision!==facts.approvedRevision)return {action:facts.canEdit?'adopt':null,label:'采用核准修订',description:'配准已核准，下一步显式采用该修订。'};
 if(facts.adoptedRevision!==null)return {action:'association',label:'前往空间关联',description:'已采用核准配准，下一步维护对象、空间关系与业务关联。'};
 return {action:null,description:'请核对当前配准资料状态。'};
}
export function registrationNextStep(facts:Facts,now=Date.now()):Next{
 if(facts.dirty)return {action:facts.canEdit?'save':null,label:'保存资料',description:'先保存当前配准资料，再提交独立审核。'};
 if(!facts.hasDocument)return {action:facts.canEdit?'import':null,label:'导入配准资料',description:'先录入控制点、检查点与坐标基准依据，核对参数。'};
 if(['draft','rejected'].includes(facts.reviewStatus))return draftStep(facts);
 if(facts.reviewStatus==='submitted')return submittedStep(facts);
 if(facts.reviewStatus==='approved')return approvedStep(facts,now);
 return {action:null,description:'请核对当前配准资料状态。'};
}
