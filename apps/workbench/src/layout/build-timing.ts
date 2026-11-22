/** Presentation estimates only. Dates never grant workflow completion or change audit records. */
export const buildTimingDefaults=[20,5,10,5] as const;
export const buildTimingReferenceSeconds=buildTimingDefaults.reduce((sum,value)=>sum+value,0)*60;
export type TimingSource='recorded'|'inferred'|'forecast';
type Boundary={at:number;source:TimingSource};
type InputTiming={registered_at?:string;registered_at_estimated?:boolean};
type JobTiming={created_at?:string;started_at?:string;finished_at?:string;state:string;demo_timeline?:{stages:{start:string;end:string;estimated:boolean}[]}};
export type BuildTimingStage={start:string;end:string;startSource:TimingSource;endSource:TimingSource;estimated:boolean;state:'complete'|'current'|'pending'|'stopped';seconds:number;referenceSeconds:number;overdue:boolean};
export type BuildTiming={stages:BuildTimingStage[];start:string;startSource:TimingSource;elapsedSeconds:number;remainingSeconds:number;totalSeconds:number;estimated:boolean;elapsedEstimated:boolean;complete:boolean;stopped:boolean;warnings:boolean};
const timestamp=(value?:string)=>{if(!value||!/(Z|[+-]\d{2}:\d{2})$/.test(value))return undefined;const parsed=Date.parse(value);return Number.isFinite(parsed)?parsed:undefined;};
const iso=(value:number)=>new Date(value).toISOString();

type Boundaries=(Boundary|undefined)[];
type Candidates=[string|undefined,TimingSource][][];
const present=(value:Boundary|undefined):value is Boundary=>!!value;

function currentStage(completed:boolean,stopped:boolean,built:boolean,hasJob:boolean,hasInput:boolean){
 if(completed)return 4;
 if(stopped)return 2;
 if(built)return 3;
 if(hasJob)return 2;
 return hasInput?1:0;
}

function assignAnchor(candidates:Candidates,boundaries:Boundaries,index:number,priority:TimingSource,clock:number){
 let warnings=false;
 for(const [value,source] of candidates[index]){
  if(!value||source!==priority)continue;
  const at=timestamp(value),previous=boundaries.slice(0,index).filter(present).at(-1);
  const next=boundaries.slice(index+1).find(present);
  const valid=at!==undefined&&at<=clock&&(!previous||at>=previous.at)&&(!next||at<=next.at);
  if(valid){boundaries[index]={at:at!,source};break;}
  warnings=true;
 }
 return warnings;
}

function readAnchors(candidates:Candidates,current:number,clock:number){
 const boundaries:Boundaries=Array(5).fill(undefined);
 let warnings=false;
 // Resolve all actual records first so an old estimate cannot displace a real event.
 for(const priority of ['recorded','inferred'] as const){
  for(let i=0;i<=current;i++){
   if(boundaries[i])continue;
   warnings=assignAnchor(candidates,boundaries,i,priority,clock)||warnings;
  }
 }
 return {boundaries,warnings};
}

function retainStop(boundaries:Boundaries,finishedAt:string|undefined,clock:number){
 const end=timestamp(finishedAt),previous=boundaries.slice(0,3).filter(present).at(-1);
 const valid=end!==undefined&&end<=clock&&(!previous||end>=previous.at);
 if(valid)boundaries[3]={at:end!,source:'recorded'};
 return !!finishedAt&&!valid;
}

function interpolate(boundaries:Boundaries,left:number,right:number,end:number,defaults:number[]){
 const start=boundaries[left]!.at,span=end-start;
 const weight=defaults.slice(left,right).reduce((sum,n)=>sum+n,0);
 let consumed=0;
 for(let i=left+1;i<right;i++){
  consumed+=defaults[i-1];boundaries[i]={at:start+span*consumed/weight,source:'inferred'};
 }
}

function fillBoundaries(boundaries:Boundaries,current:number,clock:number,defaults:number[]){
 const anchors=boundaries.map((b,i)=>b?i:-1).filter(i=>i>=0);
 if(!anchors.length)boundaries[0]={at:clock,source:'inferred'};
 else{
  for(let i=anchors[0]-1;i>=0;i--)boundaries[i]={at:boundaries[i+1]!.at-defaults[i],source:'inferred'};
  for(let a=0;a<anchors.length-1;a++)interpolate(boundaries,anchors[a],anchors[a+1],boundaries[anchors[a+1]]!.at,defaults);
 }
 for(let i=1;i<5;i++)if(!boundaries[i]){
  boundaries[i]={at:boundaries[i-1]!.at+defaults[i-1],source:i<=current?'inferred':'forecast'};
 }
 // Missing records for already finished work must not place its end in the future.
 if(current>0&&boundaries[current]!.at>clock){
  const last=anchors.at(-1)??0;
  interpolate(boundaries,last,current,clock,defaults);
  boundaries[current]={at:clock,source:'inferred'};
 }
}

function projectStage(start:Boundary,end:Boundary,index:number,current:number,stopped:boolean,clock:number,reference:number):BuildTimingStage{
 let state:BuildTimingStage['state']='pending';
 if(index<current)state='complete';
 else if(index===current)state=stopped?'stopped':'current';
 let actualEnd=end.at;
 if(state==='current'||(state==='stopped'&&end.source!=='recorded'))actualEnd=clock;
 const seconds=Math.max(0,(actualEnd-start.at)/1000);
 return {start:iso(start.at),end:iso(end.at),startSource:start.source,endSource:end.source,state,
  estimated:start.source!=='recorded'||end.source!=='recorded',seconds,referenceSeconds:reference/1000,
  overdue:state==='current'&&seconds>reference/1000};
}

function forecast(stages:BuildTimingStage[],current:number,stopped:boolean,clock:number,defaults:number[]){
 if(current>=4)return;
 const active=stages[current],start=Date.parse(active.start);
 if(stopped){
  active.end=iso(start+active.seconds*1000);
  active.endSource=active.endSource==='recorded'?'recorded':'inferred';
  active.estimated=active.startSource!=='recorded'||active.endSource!=='recorded';
 }else{
  active.end=iso(Math.max(clock,start+active.referenceSeconds*1000));
  active.endSource='forecast';active.estimated=true;
 }
 for(let i=current+1;i<4;i++){
  const nextStart=Date.parse(stages[i-1].end);
  stages[i]={...stages[i],start:iso(nextStart),end:iso(nextStart+defaults[i]),startSource:'forecast',endSource:'forecast',estimated:true,seconds:defaults[i]/1000};
 }
}

function remaining(stage:BuildTimingStage){
 if(stage.state==='pending')return stage.referenceSeconds;
 if(stage.state==='current')return Math.max(0,stage.referenceSeconds-stage.seconds);
 return 0;
}

function elapsedIsEstimated(stage:BuildTimingStage){
 if(stage.state==='pending')return false;
 if(stage.state==='complete')return stage.estimated;
 return stage.startSource!=='recorded'||(stage.state==='stopped'&&stage.endSource!=='recorded');
}

export function buildTiming({sceneCreatedAt,input,job,reviewedAt,selectedAt,publishedAt,selected=false,modelReady=false,now}: {
 sceneCreatedAt?:string;input?:InputTiming;job?:JobTiming;reviewedAt?:string;selectedAt?:string;publishedAt?:string;selected?:boolean;modelReady?:boolean;now:string;
}):BuildTiming{
 const clock=timestamp(now);
 if(clock===undefined)throw Error('invalid_timing_clock');
 const defaults=buildTimingDefaults.map(value=>value*60000);
 const completed=selected||[reviewedAt,publishedAt].some(value=>{const at=timestamp(value);return at!==undefined&&at<=clock;});
 const stopped=!!job&&['failed','interrupted','views_failed'].includes(job.state);
 const current=currentStage(completed,stopped,!!(modelReady||job?.state==='succeeded'),!!job,!!input);
 const candidates:Candidates=[
  [[sceneCreatedAt,'recorded']],
  [[input?.registered_at,input?.registered_at_estimated?'inferred':'recorded']],
  [[job?.started_at,'recorded'],[job?.created_at,'inferred']],
  [[job?.finished_at,'recorded']],
  [[reviewedAt,'recorded'],[selectedAt,'inferred'],[publishedAt,'inferred']],
 ];
 for(let i=1;i<5;i++)candidates[i].push([job?.demo_timeline?.stages[i-1]?.end,'inferred']);
 const anchors=readAnchors(candidates,current,clock),boundaries=anchors.boundaries;
 if(stopped)anchors.warnings=retainStop(boundaries,job?.finished_at,clock)||anchors.warnings;
 fillBoundaries(boundaries,current,clock,defaults);
 const stages=defaults.map((reference,i)=>projectStage(boundaries[i]!,boundaries[i+1]!,i,current,stopped,clock,reference));
 forecast(stages,current,stopped,clock,defaults);
 const elapsedSeconds=stages.filter(s=>s.state!=='pending').reduce((sum,s)=>sum+s.seconds,0);
 const remainingSeconds=stopped?0:stages.reduce((sum,s)=>sum+remaining(s),0);
 return {stages,start:stages[0].start,startSource:stages[0].startSource,elapsedSeconds,remainingSeconds,totalSeconds:elapsedSeconds+remainingSeconds,
  estimated:stages.some(s=>s.estimated),elapsedEstimated:stages.some(elapsedIsEstimated),complete:completed,stopped,warnings:anchors.warnings};
}

export function timingDuration(seconds:number){
 if(seconds>0&&seconds<60)return '不足1分钟';
 const minutes=Math.floor(Math.max(0,seconds)/60),days=Math.floor(minutes/1440),hours=Math.floor(minutes%1440/60),rest=minutes%60;
 return [days?`${days}天`:'',hours?`${hours}小时`:'',rest||!minutes?`${rest}分钟`:''].join('');
}
