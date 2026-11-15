import React,{useEffect,useRef,useState} from 'react';
import {Button,Icon,Popover,PopoverContent,PopoverTrigger,RadioGroup,RadioGroupItem,Textarea} from '@vxture/design-system';
import {CaretDown,CaretUp,ArrowUp,ArrowRight,User,CheckCircle} from '@phosphor-icons/react';
import {assistantConfirmationModes,assistantTaskSignature,matchAssistantTasks,type AssistantConfirmationMode,type AssistantReport,type AssistantTask} from './assistant-contract';

type Message={id:number;text:string;user?:boolean;tasks?:Omit<AssistantTask,'run'>[]};
export function AssistantConversation({report,onSelect}:{report:AssistantReport;onSelect:()=>void}){
 const [folded,setFolded]=useState(false),[draft,setDraft]=useState(''),[messages,setMessages]=useState<Message[]>([]),[confirmation,setConfirmation]=useState<AssistantConfirmationMode>('each'),[popup,setPopup]=useState(false),[newMessages,setNewMessages]=useState(false);
 const sequence=useRef(0),log=useRef<HTMLDivElement>(null),follow=useRef(true),input=useRef<HTMLTextAreaElement>(null),priorDraft=useRef(false);
 const current=assistantConfirmationModes.find(item=>item.id===confirmation)!;
 const tasks=report.status==='ready'?report.tasks:[];
 useEffect(()=>{const el=log.current;if(!el)return;if(follow.current)el.scrollTop=el.scrollHeight;else setNewMessages(true);},[messages]);
 useEffect(()=>{const el=input.current;if(!el)return;el.style.height='auto';el.style.height=Math.min(144,Math.max(72,el.scrollHeight))+'px';},[draft]);
 const send=()=>{
  const text=draft.trim();if(!text)return;
  const matches=matchAssistantTasks(text,report);
  const reply=report.status==='loading'?'正在读取当前业务信息，请稍后重试。':report.status==='error'?(report.note||'当前业务信息不可读取，请在业务页重试。'):matches.length?'找到以下可用操作，选择后进入业务表单继续。':tasks.length?'当前输入未匹配到可用操作。可以输入设备名称、任务名称，或输入“推荐操作”查看当前建议。':'当前页面没有可用操作建议。可在业务页面继续工作。';
  follow.current=true;setFolded(true);setDraft('');priorDraft.current=false;
  setMessages(items=>[...items,{id:++sequence.current,text,user:true},{id:++sequence.current,text:reply,tasks:matches.map(({run,...task})=>task)}]);
 };
 const openTask=(snapshot:Omit<AssistantTask,'run'>)=>{
  const latest=tasks.find(task=>assistantTaskSignature(task)===assistantTaskSignature({...snapshot,run:()=>{}}));
  if(!latest)return;
  onSelect();latest.run();
 };
 return <>
  <div className="assistant-conversation-body">
   {tasks.length>0&&<section className={`assistant-recommendations ${folded?'is-folded':''}`} aria-label="推荐操作">
    <button className="assistant-recommendation-toggle" aria-expanded={!folded} aria-controls="assistant-recommendation-list" onClick={()=>setFolded(value=>!value)}><span>推荐操作 <small>（{tasks.length}）</small></span><span>{folded?'展开':'收起'}{folded?<CaretDown size={14}/>:<CaretUp size={14}/>}</span></button>
    {!folded&&<div className="assistant-recommendation-list" id="assistant-recommendation-list" tabIndex={0}>{tasks.map(task=><details className="assistant-task" key={task.id}><summary><Icon name="list-checks" size="sm"/><span>{task.title}</span><CaretDown size={14}/></summary><div><p>{task.evidence}</p><Button variant="secondary" size="xl" onClick={()=>openTask(task)}>{task.label}<ArrowRight size={14}/></Button></div></details>)}</div>}
   </section>}
   <div className="assistant-chat" ref={log} role="log" aria-label="助手对话" aria-live="polite" tabIndex={0} onScroll={()=>{const el=log.current;if(!el)return;follow.current=el.scrollHeight-el.scrollTop-el.clientHeight<32;if(follow.current)setNewMessages(false);}}>
    <p className="assistant-chat-intro">可按设备或任务名称查找当前操作建议。选择操作后，进入业务表单继续。</p>
    {report.status==='loading'&&<p role="status">正在读取当前页面信息…</p>}
    {report.status==='error'&&<p role="alert">{report.note||'当前业务信息不可读取。'}</p>}
    {report.status==='ready'&&report.note&&<p className="assistant-report-note">{report.note}</p>}
    {messages.map(message=><div key={message.id} className={message.user?'assistant-chat-message is-user':'assistant-chat-message'}>
     {message.user&&<User size={16} className="assistant-user-avatar" aria-label="你发送的消息"/>}<p>{message.text}</p>
     {message.tasks?.map(task=>{const valid=tasks.some(item=>assistantTaskSignature(item)===assistantTaskSignature({...task,run:()=>{}}));return <article className="assistant-action-card" key={task.id}><h3>{task.title}</h3><p>{task.evidence}</p><footer><small>{valid?'由业务表单校验权限并确认':'页面数据已变化，请重新查找'}</small><Button variant="secondary" size="xl" disabled={!valid} onClick={()=>openTask(task)}>{task.label}<ArrowRight size={14}/></Button></footer></article>;})}
    </div>)}
   </div>
   {newMessages&&<Button className="assistant-new-messages" variant="secondary" size="sm" onClick={()=>{follow.current=true;setNewMessages(false);log.current?.scrollTo({top:log.current.scrollHeight,behavior:'smooth'});}}>有新消息 ↓</Button>}
  </div>
  <form className="assistant-input" onSubmit={event=>{event.preventDefault();send();}}>
   <Textarea ref={input} aria-label="向助手描述任务" placeholder="输入设备或任务名称…" value={draft} maxLength={2000} onChange={event=>{const text=event.target.value;setDraft(text);if(text.trim()&&!priorDraft.current)setFolded(true);priorDraft.current=!!text.trim();}} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();send();}}}/>
   <div><small>当前支持业务建议检索</small><Button type="submit" size="icon-xl" disabled={!draft.trim()} aria-label="发送任务"><ArrowUp size={16}/></Button></div>
  </form>
  <footer className="workspace-assistant-footer"><Popover open={popup} onOpenChange={setPopup}><PopoverTrigger asChild><Button variant="ghost" size="xl" className="assistant-mode-trigger"><Icon name={current.icon} size="sm"/>{current.label}<CaretUp size={12}/></Button></PopoverTrigger><PopoverContent side="top" align="start" sideOffset={8} className="assistant-mode-popup" aria-label="授权方式"><h3>授权方式</h3><RadioGroup value={confirmation} onValueChange={value=>{setConfirmation(value as AssistantConfirmationMode);setPopup(false);}} aria-label="选择授权方式">{assistantConfirmationModes.map(item=><label className="assistant-mode-option" key={item.id} data-selected={confirmation===item.id}><Icon name={item.icon} size="md"/><span><strong>{item.label}</strong><small>{item.description}</small></span><RadioGroupItem value={item.id} aria-label={item.label}/></label>)}</RadioGroup><p>删除、覆盖等高危操作仍需确认。</p><small>当前业务操作仍在表单中确认，模式不扩大权限。</small></PopoverContent></Popover><span><CheckCircle size={12}/>权限范围内</span></footer>
 </>;
}
