import React,{lazy,Suspense,useEffect,useRef,useState} from 'react';
import {Button,Icon,NativeSelect} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {readPreview} from './geometry-preview-data';
import {frameAt,validateProcess,type ProcessData,type ProcessPlayback} from './build-process-data';
import {type BuildStages,viewState} from './view-derivations';
import {BuildSource} from './rgbd-preview';
const Canvas=lazy(()=>import('./geometry-preview-canvas'));
const labels:Record<string,string>={queued:'排队中',running:'构建中',succeeded:'候选已就绪',views_failed:'视图待恢复',failed:'构建失败',interrupted:'构建已中断'};
export function BuildProcess({space,job,input}:{space:string;job:string;input:string}){
 const [data,setData]=useState<ProcessData|null>(null),[initial,setInitial]=useState<ProcessData|null>(null),[error,setError]=useState(''),[name,setName]=useState('场景空间'),[state,setState]=useState(''),[stages,setStages]=useState<BuildStages|null>(null),[retry,setRetry]=useState(0);
 const [following,setFollowing]=useState(true),[playing,setPlaying]=useState(false),[cursor,setCursor]=useState(0),[speed,setSpeed]=useState(.1);
 const latest=useRef<ProcessData|null>(null),follow=useRef(true),playback=useRef<ProcessPlayback>({frame:0,data:null!});follow.current=following;
 const frame=data?.frames.length?frameAt(data,cursor):0,duration=data?.frames.at(-1)?.relative_time_us||0;
 if(data)playback.current={frame,data};
 useEffect(()=>{if(!playing||!duration)return;let previous=performance.now(),id=0;const tick=(now:number)=>{const delta=Math.min(now-previous,250);previous=now;setCursor(t=>Math.min(duration,t+delta*1000*speed));id=requestAnimationFrame(tick);};id=requestAnimationFrame(tick);return()=>cancelAnimationFrame(id);},[playing,speed,duration]);
 useEffect(()=>{if(duration&&cursor>=duration)setPlaying(false);},[cursor,duration]);
 useEffect(()=>{
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined,first=true;latest.current=null;setData(null);setInitial(null);setError('');setFollowing(true);setPlaying(false);setCursor(0);
  const read=async(path:string)=>{const r=await fetch(businessEndpoint+path,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error(r.status===403?'当前账户无权查看此构建。':'构建记录暂不可用，请重试。');return r.json();};
  const poll=async()=>{try{
   const q=new URLSearchParams({space_id:space,candidate_id:job});
   const [list,stage]=await Promise.all([read('/api/builds?'+new URLSearchParams({space_id:space})),read('/api/build-stages?'+q)]);
   const record=list.jobs?.find((r:{id:string;space_id:string;input_id:string})=>r.id===job&&r.space_id===space&&r.input_id===input);
   if(!record||stage.space_id!==space||stage.job_id!==job||!['cospace.build-process/0.1','cospace.lidar-build-process/0.1'].includes(record.process_profile))throw Error('构建过程与当前任务不一致。');
   const checked=validateProcess(await readPreview(businessEndpoint+'/api/build-process?'+q,controller.signal),{space,job,input,snapshot:record.input_binding.snapshot_sha256,tracking:record.input_binding.tracking_sha256,bag:record.input_binding.bag_sha256,model:stage.frozen_model?.source_model_sha256});
   if(controller.signal.aborted)return;setState(record.state);setStages(stage);setError('');
   if(checked.ready){
    if(latest.current&&checked.revision<latest.current.revision)throw Error('构建过程修订无效。');
    if(!latest.current||checked.revision!==latest.current.revision||checked.state!==latest.current.state||checked.job_state!==latest.current.job_state){
     latest.current=checked;setData(checked);if(checked.point_count)setInitial(v=>v||checked);
     if(first&&checked.state==='completed'){setFollowing(false);setCursor(0);setPlaying(!matchMedia('(prefers-reduced-motion: reduce)').matches);}
     else if(follow.current){setCursor(checked.frames.at(-1)?.relative_time_us||0);if(checked.state!=='recording')setFollowing(false);}
     first=false;
    }
   }
   if(['queued','running'].includes(record.state))timer=setTimeout(poll,1000);
  }catch(e){if(!controller.signal.aborted){const message=e instanceof Error?e.message:'过程读取失败。';setError(message);setPlaying(false);if(/无权|校验|无效|不一致/.test(message)){latest.current=null;setData(null);setInitial(null);}}}};
  void poll();void read('/api/spaces/'+encodeURIComponent(space)).then(s=>{if(!controller.signal.aborted&&s.id===space)setName(s.name||s.label||'场景空间');}).catch(()=>{});
  return()=>{controller.abort();clearTimeout(timer);};
 },[space,job,input,retry]);
 const back=`./layout.html#build?${new URLSearchParams({space,job,input,tab:'flow'})}`;
 return <main className="build-scan dark" aria-label="全屏构建画布">
  {initial&&data&&<Suspense fallback={<p className="build-scan-message" role="status">正在打开空间画布…</p>}><Canvas data={initial} process={playback}/></Suspense>}
  <div className="build-scan-top"><div className="build-scan-title"><Icon name="cube" size="sm"/><span>{name}</span><span className="build-scan-divider"/><span className="build-scan-mode">{following?'跟随构建':'过程回放'}</span></div><Button asChild size="sm" variant="ghost"><a href={back} aria-label="返回构建流程"><Icon name="arrow-left" size="sm"/>构建流程</a></Button></div>
  <div className="build-scan-stages" aria-label="真实构建状态"><span className="build-scan-dot"/>{labels[state]||'读取任务'}<span>模型 {stages?.frozen_model?'已冻结':'待生成'}</span><span>人视图 {viewState(stages?.views.human?.state)}</span><span>智能体 {viewState(stages?.views.agent?.state)}</span></div>
  {data?.profile==='cospace.build-process/0.1'&&data?.frames[frame]&&<BuildSource endpoint={businessEndpoint} binding={{space,input,snapshot:data.snapshot_sha256,tracking:data.tracking_sha256}} process={data.frames[frame]}/>}
  {!initial&&!error&&<div className="build-scan-message" role="status"><Icon name="cube"/><p>{['failed','interrupted'].includes(state)?'构建已停止，尚无已保存的过程几何。':'等待工作进程保存首帧点云…'}</p></div>}
  {error&&<div className="build-process-error" role="alert"><span>{error}{data?' 已暂停在最后核验画面。':''}</span><Button size="sm" variant="outline" onClick={()=>setRetry(n=>n+1)}>重新读取</Button></div>}
  {data&&data.frames.length>0&&<div className="build-scan-bottom build-process-bottom"><div className="build-scan-player" role="group" aria-label="构建回放控制">
   <Button size="sm" variant="ghost" aria-label={playing?'暂停回放':'播放回放'} onClick={()=>{setFollowing(false);if(cursor>=duration)setCursor(0);setPlaying(v=>!v);}}><Icon name={playing?'pause':'play'} size="sm"/></Button>
   <Button size="sm" variant="ghost" aria-label="重新回放" onClick={()=>{setFollowing(false);setCursor(0);setPlaying(true);}}><Icon name="clock-counter-clockwise" size="sm"/></Button>
   <input type="range" aria-label="构建源时间" min="0" max={Math.max(duration,1)} step="1" value={cursor} onChange={e=>{setFollowing(false);setPlaying(false);setCursor(Number(e.target.value));}}/>
   <span className="build-process-time">{(cursor/1e6).toFixed(2)}s</span>
   <NativeSelect aria-label="回放速度" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={.1}>0.1×</option><option value={.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option></NativeSelect>
   {state==='running'&&<Button size="sm" variant={following?'secondary':'ghost'} aria-label="跟随最新构建" onClick={()=>{setPlaying(false);setFollowing(true);setCursor(duration);}}><Icon name="arrow-right" size="sm"/></Button>}
  </div><div className="build-process-caption"><span>第 {frame+1} 帧 · 已处理 {data.processed_frames}/{data.available_frames} 帧{data.excluded_frames>0?` · ${data.excluded_frames} 帧未参与`:''}</span><span>{data.state==='failed'||data.state==='interrupted'?'构建中断 · 已保存部分':following?'已保存进展':'相对源时间'}</span></div><p className="build-scan-basis">{data.profile==='cospace.lidar-build-process/0.1'?'预录激光 · 本次估计轨迹 · 非实时采集':'预录 RGB-D · 估计相机位姿 · 非实时采集'}<span>显示抽样 {data.sampling.count.toLocaleString()} 点</span></p></div>}
 </main>;
}
