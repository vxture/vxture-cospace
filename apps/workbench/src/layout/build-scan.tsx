import React,{lazy,Suspense,useEffect,useMemo,useRef,useState} from 'react';
import {Button,Icon,NativeSelect} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {readPreview,validatePreview,PreviewResponse} from './geometry-preview-data';
import {BuildStages} from './view-derivations';
import {scanOrder} from './build-scan-data';
import './build-scan.css';
import {BuildProcess} from './build-process';
const Canvas=lazy(()=>import('./geometry-preview-canvas'));
const labels:Record<string,string>={queued:'排队中',running:'构建中',succeeded:'候选已就绪',views_failed:'视图待恢复',failed:'构建失败',interrupted:'构建已中断'};

export function BuildScan(){
 const params=new URLSearchParams(location.search),space=params.get('space')||'',job=params.get('job')||'',input=params.get('input')||'';
 const [mode,setMode]=useState<'loading'|'static'|'process'|'error'>('loading'),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{const controller=new AbortController();setMode('loading');
  void fetch(businessEndpoint+'/api/builds?'+new URLSearchParams({space_id:space}),{signal:controller.signal,cache:'no-store'}).then(async r=>{
   if(!r.ok)throw Error(r.status===403?'当前账户无权查看此构建。':'构建记录暂不可用，请重试。');
   const list=await r.json(),record=list.jobs?.find((v:{id:string;space_id:string;input_id:string})=>v.id===job&&v.space_id===space&&v.input_id===input);
   if(!space||!job||!input||!record)throw Error('缺少明确的场景、资料或构建任务，或归属不一致。');
   if(!controller.signal.aborted)setMode(['cospace.build-process/0.1','cospace.lidar-build-process/0.1'].includes(record.process_profile)?'process':'static');
  }).catch(e=>{if(!controller.signal.aborted){setError(e.message);setMode('error');}});return()=>controller.abort();
 },[space,job,input,retry]);
 if(mode==='process')return <BuildProcess key={job} space={space} job={job} input={input}/>;
 if(mode==='static')return <StaticBuildScan/>;
 return <main className="build-scan dark" aria-label="全屏构建画布"><div className="build-scan-message" role={mode==='error'?'alert':'status'}><p>{mode==='error'?error:'正在读取构建任务…'}</p>{mode==='error'&&<Button size="sm" variant="outline" onClick={()=>setRetry(n=>n+1)}>重新读取</Button>}<Button asChild size="sm" variant="ghost"><a href={`./layout.html#build?${new URLSearchParams({space,job,input,tab:'flow'})}`}>返回构建流程</a></Button></div></main>;
}
function StaticBuildScan(){
 const params=new URLSearchParams(location.search),space=params.get('space')||'',job=params.get('job')||'',input=params.get('input')||'';
 const [data,setData]=useState<PreviewResponse|null>(null),[error,setError]=useState(''),[state,setState]=useState(''),[name,setName]=useState('场景空间'),[stages,setStages]=useState<BuildStages|null>(null),[retry,setRetry]=useState(0);
 const [playing,setPlaying]=useState(false),[progress,setProgress]=useState(0),[speed,setSpeed]=useState(1);
 const playback=useRef({progress:0});playback.current.progress=progress;
 const ordered=useMemo(()=>data?scanOrder(data):null,[data]);
 useEffect(()=>{if(!playing)return;let previous=performance.now(),frame=0;const tick=(now:number)=>{const delta=Math.min(now-previous,250);previous=now;setProgress(v=>Math.min(1,v+delta*speed/24000));frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame);},[playing,speed]);
 useEffect(()=>{if(progress>=1)setPlaying(false);},[progress]);
 useEffect(()=>{const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined,loaded=false;setError('');setData(null);setPlaying(false);setProgress(0);
  const read=async(path:string)=>{const r=await fetch(businessEndpoint+path,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error(r.status===403?'当前账户无权查看此构建。':'构建记录暂不可用，请重试。');return r.json();};
  const poll=async()=>{try{
   if(!space||!job||!input)throw Error('缺少明确的场景、资料或构建任务。');
   const [jobList,stage]=await Promise.all([read('/api/builds?'+new URLSearchParams({space_id:space})),read('/api/build-stages?'+new URLSearchParams({space_id:space,candidate_id:job}))]);
   const record=jobList.jobs?.find((j:{id:string;input_id:string;space_id:string})=>j.id===job&&j.input_id===input&&j.space_id===space);
   if(!record||stage.space_id!==space||stage.job_id!==job)throw Error('构建与当前场景或资料不一致。');
   if(controller.signal.aborted)return;setState(record.state);setStages(stage);
   if(stage.frozen_model&&!loaded){
    const v=await readPreview(`${businessEndpoint}/api/build-preview?${new URLSearchParams({space_id:space,candidate_id:job,kind:'model'})}`,controller.signal);
    const geometry=validatePreview(v,{space,input,job,kind:'model',source:stage.frozen_model.source_model_sha256,manifest:stage.frozen_model.manifest_sha256});
    if(!controller.signal.aborted){setData(geometry);loaded=true;setPlaying(!matchMedia('(prefers-reduced-motion: reduce)').matches);}
   }
   if(['queued','running'].includes(record.state))timer=setTimeout(poll,3000);
  }catch(e){if(!controller.signal.aborted){setPlaying(false);setData(null);setError(e instanceof Error?e.message:'构建无法读取。');}}};
  void poll();void read('/api/spaces/'+encodeURIComponent(space)).then(s=>{if(!controller.signal.aborted&&s.id===space)setName(s.name||s.label||'场景空间');}).catch(()=>{});
  return()=>{controller.abort();clearTimeout(timer);};
 },[space,job,input,retry]);
 const back=`./layout.html#build?${new URLSearchParams({space,job,input,tab:'flow'})}`;
 return <main className="build-scan build-scan-static dark" aria-label="全屏构建画布">
  {ordered&&<Suspense fallback={<p className="build-scan-message" role="status">正在打开空间画布…</p>}><Canvas data={ordered} scan={playback}/></Suspense>}
  <div className="build-scan-top"><div className="build-scan-title"><Icon name="cube" size="sm"/><span>{name}</span><span className="build-scan-divider"/><span className="build-scan-mode">扫描效果演示</span></div><Button asChild size="sm" variant="ghost"><a href={back} aria-label="返回构建流程"><Icon name="arrow-left" size="sm"/>构建流程</a></Button></div>
  <div className="build-scan-stages" aria-label="真实构建状态"><span className="build-scan-dot"/>{labels[state]||'读取任务'}<span>模型 {stages?.frozen_model?'已冻结':'待生成'}</span><span>人视图 {stages?.views.human?.state==='succeeded'?'已派生':stages?.views.human?.state==='failed'?'失败':stages?.views.human?.state==='running'?'派生中':'待派生'}</span><span>智能体 {stages?.views.agent?.state==='succeeded'?'已派生':stages?.views.agent?.state==='failed'?'失败':stages?.views.agent?.state==='running'?'派生中':'待派生'}</span></div>
  {!ordered&&<div className="build-scan-message" role={error?'alert':'status'}><Icon name="cube"/><p>{error||(['failed','interrupted','views_failed'].includes(state)?'本次构建已停止，尚无可显示的固定模型。':'等待模型冻结后展示空间。')}</p>{error&&<Button size="sm" variant="outline" onClick={()=>setRetry(n=>n+1)}>重新读取</Button>}</div>}
  {ordered&&<div className="build-scan-bottom"><div className="build-scan-player" role="group" aria-label="扫描演示控制"><Button size="sm" variant="ghost" aria-label={playing?'暂停演示':'播放演示'} onClick={()=>{if(progress>=1)setProgress(0);setPlaying(v=>!v);}}><Icon name={playing?'pause':'play'} size="sm"/></Button><Button size="sm" variant="ghost" aria-label="重新演示" onClick={()=>{setProgress(0);setPlaying(true);}}><Icon name="clock-counter-clockwise" size="sm"/></Button><input type="range" aria-label="演示进度" min="0" max="1000" value={Math.round(progress*1000)} onChange={e=>{setPlaying(false);setProgress(Number(e.target.value)/1000);}}/><span className="build-scan-percent">{Math.round(progress*100)}%</span><NativeSelect aria-label="演示速度" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option></NativeSelect></div><p className="build-process-caption">此任务未记录逐帧过程</p><p className="build-scan-basis">已有点云按方位渐显 · 非采集时间或机器人轨迹<span>主体视角 · {data?.sampling.count.toLocaleString()} 点</span></p></div>}
 </main>;
}
