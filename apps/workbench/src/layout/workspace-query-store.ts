export type QuerySnapshot<T>={data:T|null;loading:boolean;error:string;revision:number};
type Entry<T>={snapshot:QuerySnapshot<T>;expires:number;pending:Promise<void>|null;listeners:Set<()=>void>};
// Per application/scope, never persistent browser storage. Invalidated generations
// reject late responses, even when the transport cannot cancel an in-flight read.
export class WorkspaceQueryStore{
 private entries=new Map<string,Entry<unknown>>();
 private generation=0;
 private now:()=>number;
 constructor(now:()=>number=()=>performance.now()){this.now=now;}
 private entry<T>(key:string):Entry<T>{
  if(!this.entries.has(key))this.entries.set(key,{snapshot:{data:null,loading:true,error:'',revision:0},expires:0,pending:null,listeners:new Set()});
  return this.entries.get(key) as Entry<T>;
 }
 snapshot<T>(key:string){return this.entry<T>(key).snapshot;}
 subscribe(key:string,fn:()=>void){const entry=this.entry(key);entry.listeners.add(fn);return()=>{entry.listeners.delete(fn);};}
 async read<T>(key:string,load:()=>Promise<T>,maxAge=15000){
  const entry=this.entry<T>(key);
  if(entry.pending)return entry.pending;
  if(entry.expires>this.now())return;
  const generation=this.generation,revision=entry.snapshot.revision;
  // Retain a valid same-scope value while refreshing; unknown is never "absent".
  entry.snapshot={...entry.snapshot,loading:true,error:''};entry.listeners.forEach(fn=>fn());
  entry.pending=Promise.resolve().then(load).then(data=>{
   if(generation!==this.generation||revision!==entry.snapshot.revision)return;
   entry.snapshot={data,loading:false,error:'',revision};entry.expires=this.now()+maxAge;
  }).catch(error=>{
   if(generation!==this.generation||revision!==entry.snapshot.revision)return;
   entry.snapshot={data:null,loading:false,error:error instanceof Error?error.message:'数据暂不可用',revision};entry.expires=0;
  }).finally(()=>{
   // An invalidation can start a replacement request before this one settles.
   if(generation!==this.generation||revision!==entry.snapshot.revision)return;
   entry.pending=null;entry.listeners.forEach(fn=>fn());
   this.prune();
  });
  return entry.pending;
 }
 invalidate(){
  this.generation++;
  for(const entry of this.entries.values()){
   entry.expires=0;entry.pending=null;
   entry.snapshot={data:null,loading:true,error:'',revision:entry.snapshot.revision+1};
   entry.listeners.forEach(fn=>fn());
  }
  this.prune();
 }
 private prune(){if(this.entries.size>128)for(const [key,entry] of this.entries){if(!entry.listeners.size&&!entry.pending)this.entries.delete(key);if(this.entries.size<=128)break;}}
}
