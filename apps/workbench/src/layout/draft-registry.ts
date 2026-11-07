export type Draft={label:string;save?:()=>Promise<boolean>;discard?:()=>void;canSave?:boolean};
// Only memory owned by this tab. No credentials, drafts or callbacks in storage.
export class DraftRegistry{
 entries=new Map<symbol,Draft>();
 epoch=0;
 clear(){this.epoch++;this.entries.clear();}
 set(id:symbol,value:Draft|null){if(value)this.entries.set(id,value);else this.entries.delete(id);}
 list(){return [...this.entries.entries()];}
 async saveAll(){
  const epoch=this.epoch,entries=this.list();
  if(entries.some(([,draft])=>!draft.save||draft.canSave===false))return false;
  for(const [id,draft] of entries){
   if(!draft.save||draft.canSave===false)return false;
   if(!await draft.save()||this.epoch!==epoch)return false;
   this.entries.delete(id);
  }
  return true;
 }
 discardAll(){for(const [id,draft] of this.list()){draft.discard?.();this.entries.delete(id);}}
}
