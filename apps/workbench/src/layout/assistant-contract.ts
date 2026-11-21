export type AssistantTask={id:string;title:string;evidence:string;label:string;run:()=>void;tone?:'warning'|'danger'};
export type AssistantReport={title:string;status:'loading'|'ready'|'error';note?:string;tasks:AssistantTask[]};

export function assistantAvailable(route:string){return !['','home','space'].includes(route);}
export function assistantScope(route:string,url:string,session:string){return JSON.stringify([session,route,url]);}
// Suggestions hand off to existing business forms. They never bypass their
// authorization, validation, unsaved-change guards or destructive confirmations.
export function buildAssistantReport(facts:{loading:boolean;error:string;canBuild:boolean;canRegister:boolean;inputs:number;state?:string;model:boolean;selected:boolean},act:(step:string)=>void):AssistantReport{
 if(facts.loading)return {title:'构建检查',status:'loading',tasks:[]};
 if(facts.error)return {title:'构建检查',status:'error',note:facts.error,tasks:[]};
 if(!facts.canBuild)return {title:'构建检查',status:'ready',note:'当前身份没有构建权限。',tasks:[]};
 const task=(id:string,title:string,evidence:string,label:string):AssistantTask=>({id,title,evidence,label,run:()=>act(id)});
 const tasks:AssistantTask[]=[];
 if(!facts.inputs)tasks.push(task('prepare','准备构建资料','当前场景还没有登记输入资料。','准备资料'));
 else if(!facts.state)tasks.push(task('check','检查本次资料','资料已登记，提交构建前需完成预检。','进入预检'));
 else if(['failed','interrupted','views_failed'].includes(facts.state))tasks.push({...task('model','处理构建异常','当前构建未完整完成，请核查阶段记录与恢复选项。','核查构建'),tone:'warning'});
 else if(['running','queued'].includes(facts.state))tasks.push(task('model','跟进构建进展','当前构建正在执行或排队。','查看进展'));
 else if(facts.model&&!facts.selected)tasks.push(task('review','核对构建成果','模型已生成，尚未选择为当前候选。','核对成果'));
 else if(facts.model&&facts.canRegister)tasks.push(task('registration','核对空间配准','当前构建成果已核对并选择，继续核对该模型的坐标基准与地图配准。','前往空间配准'));
 return {title:'构建检查',status:'ready',note:tasks.length?undefined:'当前构建暂无待处理事项。',tasks};
}

export const assistantConfirmationModes=[
 {id:'each',label:'逐项确认',description:'每项操作前请你确认。',icon:'list-checks'},
 {id:'routine',label:'常规授权',description:'常规自动，重要或存疑时确认。',icon:'target'},
 {id:'full',label:'充分授权',description:'授权范围内自动执行。',icon:'agent'},
] as const;
export type AssistantConfirmationMode=typeof assistantConfirmationModes[number]['id'];
/** Match only current, readable suggestions. Never infer new executable actions. */
export function matchAssistantTasks(text:string,report:AssistantReport):AssistantTask[]{
 if(report.status!=='ready')return [];
 const query=text.trim().toLowerCase();
 if(!query)return [];
 if(/^(推荐|推荐操作|待办|待处理|有什么任务|全部任务)[？?。!！]*$/.test(query))return report.tasks;
 const phrases=query.match(/[a-z0-9]+|[\u4e00-\u9fff]+/g)||[];
 const terms=phrases.flatMap(word=>/^[a-z0-9]+$/.test(word)?[word]:Array.from({length:Math.max(0,word.length-1)},(_,i)=>word.slice(i,i+2)));
 const scored=report.tasks.map(task=>({task,score:terms.filter(term=>`${task.title} ${task.evidence} ${task.label}`.toLowerCase().includes(term)).length}));
 const maximum=Math.max(0,...scored.map(item=>item.score));
 return maximum?scored.filter(item=>item.score===maximum).map(item=>item.task):[];
}
export function assistantTaskSignature(task:AssistantTask){return JSON.stringify([task.id,task.title,task.evidence,task.label]);}
