export type OperationDetails={verb:string;target:string;consequence:string;preconditions?:readonly {label:string;met:boolean;unknown?:boolean;note?:string}[]};
type Pending=OperationDetails&{owner:symbol;epoch:number;execute:()=>unknown|Promise<unknown>;resolve:(ok:boolean)=>void;running:boolean};

/** One reviewable operation at a time. Invalidated owners can never execute. */
export class OperationConfirmationStore{
 private pending:Pending|null=null;
 private epoch=0;
 private listeners=new Set<()=>void>();
 snapshot=()=>this.pending;
 subscribe=(listener:()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener);};};
 private changed(){this.listeners.forEach(listener=>listener());}
 request(owner:symbol,details:OperationDetails,execute:()=>unknown|Promise<unknown>):Promise<boolean>{
  if(this.pending)return Promise.resolve(false);
  return new Promise(resolve=>{this.pending={...details,owner,epoch:this.epoch,execute,resolve,running:false};this.changed();});
 }
 cancel(owner?:symbol){
  if(!owner)this.epoch++;
  const current=this.pending;if(!current||(owner&&owner!==current.owner))return;
  this.pending=null;
  // Successful saves may unmount their editor before the async receipt returns.
  // Owner cleanup hides the dialog but must let that receipt settle save-and-leave.
  // A route/identity reset (no owner) still invalidates the acknowledgement now.
  if(!owner||!current.running)current.resolve(false);
  this.changed();
 }
 async commit(expected:Pending){
  if(this.pending!==expected||expected.running||expected.preconditions?.some(p=>!p.met))return;
  expected.running=true;
  try{
   const result=await expected.execute();
   if(result===false)throw Error('操作未完成，请取消后核对页面提示。');
   if(this.pending===expected){this.pending=null;this.changed();}
   expected.resolve(expected.epoch===this.epoch);
  }catch(error){
   if(this.pending!==expected)expected.resolve(false);
   throw error;
  }finally{expected.running=false;}
 }
}
