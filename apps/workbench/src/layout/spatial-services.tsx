import React,{useMemo,useState} from 'react';
import {Button,Input,NativeSelect,ViewHeader,Card,CardHeader,CardTitle,CardContent,StatusBadge,Drawer} from '@vxture/design-system';
import {Globe,Cube,Code,DownloadSimple,MagnifyingGlass,ArrowsClockwise,ArrowSquareOut,Copy} from '@phosphor-icons/react';
import {useSceneDirectory} from './use-scene-directory';
import {spatialServices,filterSpatialServices,serviceKinds,serviceResourcePath,type SpatialService} from './spatial-service-contract';
import {realScreenHref} from './real-space-data';
import {businessEndpoint} from './business-endpoint';
import {PreviewConsumerGuide} from './preview-consumer-guide';
import {PreviewRangeQuery} from './preview-range-query';
import './scene-catalog.css';
import './spatial-services.css';

const symbols={preview:Cube,query:Code,offline:DownloadSimple};
const stateLabels={active:'可用',paused:'已暂停',retired:'已退役',unknown:'待核对'};
function ServiceAction({item}:{item:SpatialService}){
 const label=item.kind==='preview'?'打开预览':item.kind==='query'?'查看接入':'下载交付包';
 if(!item.available)return <Button size="xl" disabled>{stateLabels[item.state]}</Button>;
 if(item.kind==='query')return null;
 return <Button size="xl" asChild><a href={item.kind==='preview'?realScreenHref(item.scene.id,item.release.id):businessEndpoint+serviceResourcePath(item)} target="_blank" rel="noopener noreferrer">{label}{item.kind==='preview'?<ArrowSquareOut size={16}/>:<DownloadSimple size={16}/>}</a></Button>;
}
function ServiceDetail({item,onClose}:{item?:SpatialService;onClose:()=>void}){
 const [copyState,setCopyState]=useState('');
 const path=item&&serviceResourcePath(item),url=path&&businessEndpoint+path;
 async function copy(){try{await navigator.clipboard.writeText(url!);setCopyState('已复制服务地址');}catch{setCopyState('复制未完成，请选择地址手动复制');}}
 return <Drawer open={!!item} onClose={onClose} side="right" width="lg" title="服务详情" description={item?`${item.scene.name} · ${serviceKinds[item.kind].label}`:undefined} closeLabel="关闭服务详情" className="spatial-service-detail" footer={<><Button size="xl" variant="secondary" onClick={onClose}>关闭</Button>{item&&<ServiceAction item={item}/>}</>}>
  {item&&<div className="flex flex-col gap-xl">
   <section className="flex flex-col gap-sm"><div className="flex items-center justify-between gap-md"><h2 className="text-heading-3">{serviceKinds[item.kind].label}</h2><StatusBadge tone={item.available?'success':'neutral'}>{stateLabels[item.state]}</StatusBadge></div><p className="text-body-small text-muted-foreground">{item.scene.description||'此服务基于场景的固定发布版本提供。'}</p></section>
   <section className="flex flex-col gap-md"><h3 className="text-body font-medium">版本与范围</h3><dl className="spatial-service-metadata"><dt>覆盖场景</dt><dd>{item.scene.name}</dd><dt>所属项目</dt><dd>{item.scene.project_name||'未指定项目'}</dd><dt>固定版本</dt><dd>{item.release.id}</dd><dt>发布时间</dt><dd>{new Date(item.release.created_at).toLocaleString('zh-CN',{hour12:false})}</dd><dt>使用权限</dt><dd>{serviceKinds[item.kind].label} · 当前账号已授权</dd></dl><p className="text-label-small text-muted-foreground">固定版本不会随新发布自动切换。暂停或退役后停止使用该版本，服务端会再次校验授权与发布状态。</p></section>
   {item.available?<section className="flex flex-col gap-md" aria-label="服务接入"><h3 className="text-body font-medium">接入支持</h3><p className="text-body-small text-muted-foreground">{item.kind==='preview'?'在浏览器中打开人视图与机视图，使用当前平台账号访问。':item.kind==='query'?'范围查询返回固定坐标系中的表面证据。先读取空间描述中的 frame_id，再提交范围参数。':'下载固定版本交付包，再按下方说明在使用端安装、激活和恢复。'}</p><div className="flex items-start gap-sm"><code className="spatial-service-address">{url}</code><Button size="icon-xl" variant="secondary" aria-label="复制服务地址" onClick={copy}><Copy size={16}/></Button></div>{copyState&&<p role="status" className="text-body-small">{copyState}</p>}
    {item.kind==='query'&&<><p className="text-label-small text-muted-foreground">同源浏览器调用使用当前登录会话；跨系统接入需由管理员配置服务身份。不要复制登录 Cookie 或将账号凭据写入调用代码。</p><pre className="spatial-service-example" aria-label="范围查询示例">{`POST ${path}\nContent-Type: application/json\n\n${JSON.stringify({frame_id:'替换为空间描述的 frame_id',bounds_m:[[0,0,0],[1,1,1]],limit:1024},null,2)}`}</pre><p className="text-label-small text-muted-foreground">范围采用米制坐标，最小值包含、最大值不包含；未列出的空间保持未知，不表示可通行。</p>{item.scene.capabilities?.includes('space.preview')&&<><p className="text-body-small">可在当前会话中试用查询：</p><PreviewRangeQuery key={item.id} publication={item.release.id}/></>}</>}
    {item.kind==='offline'&&<PreviewConsumerGuide key={item.id} publication={item.release.id} space={item.scene.id}/>}
    <p className="text-label-small text-muted-foreground">精度与设备适用性待验收，空间证据不作为安全导航或测绘验收依据。</p>
   </section>:<p className="text-body-small text-muted-foreground" role="status">此版本{stateLabels[item.state]}，接入操作已停用。请联系服务提供方确认可用版本。</p>}
  </div>}
 </Drawer>;
}
export function SpatialServices(){
 const [revision,setRevision]=useState(0),[query,setQuery]=useState(''),[kind,setKind]=useState('all'),[state,setState]=useState('available'),[selected,setSelected]=useState('');
 const {spaces,loading,error}=useSceneDirectory(revision);
 const items=useMemo(()=>spatialServices(spaces),[spaces]);
 const visible=useMemo(()=>filterSpatialServices(items,query,kind,state),[items,query,kind,state]);
 const detail=!error?items.find(item=>item.id===selected):undefined;
 return <main className="scene-catalog spatial-services" aria-label="空间服务"><div className="scene-catalog-shell">
  <ViewHeader title="空间服务" secondary={<span className="scene-total" aria-label="服务总数">{items.length}</span>} description="查找已授权的空间服务，获取预览、查询与交付支持。" action={<Button asChild size="xl" variant="secondary"><a href="/space">我的场景</a></Button>}/>
  <div className="scene-catalog-toolbar" aria-label="空间服务筛选"><span className="scene-result-count" aria-live="polite">筛选 <strong>{visible.length}</strong> 项</span><div className="scene-catalog-filters"><div className="scene-catalog-search"><MagnifyingGlass size={16}/><Input aria-label="搜索空间服务" placeholder="搜索场景、项目或版本" value={query} onChange={e=>setQuery(e.target.value)}/></div><NativeSelect wrapperClassName="scene-catalog-select" aria-label="服务类型" value={kind} onChange={e=>setKind(e.target.value)}><option value="all">全部类型</option>{Object.entries(serviceKinds).map(([key,item])=><option key={key} value={key}>{item.label}</option>)}</NativeSelect><NativeSelect wrapperClassName="scene-catalog-select" aria-label="服务状态" value={state} onChange={e=>setState(e.target.value)}><option value="available">可用服务</option><option value="all">全部状态</option><option value="unavailable">不可用服务</option></NativeSelect><Button size="icon-xl" variant="outline" aria-label="刷新空间服务" onClick={()=>setRevision(v=>v+1)}><ArrowsClockwise size={16}/></Button></div></div>
  {loading?<p role="status" className="scene-catalog-empty">正在读取空间服务…</p>:error?<div role="alert" className="scene-catalog-empty"><p>{error}</p><Button size="xl" variant="secondary" onClick={()=>setRevision(v=>v+1)}>重新加载</Button></div>:<div className="spatial-service-grid">{visible.map(item=>{const Symbol=symbols[item.kind];return <Card key={item.id} className="spatial-service-card"><CardHeader><div className="flex items-center justify-between gap-md"><span className="spatial-service-symbol"><Symbol size={22}/></span><StatusBadge tone={item.available?'success':'neutral'}>{stateLabels[item.state]}</StatusBadge></div><CardTitle className="text-heading-3">{item.scene.name}</CardTitle><p className="text-body-small text-muted-foreground">{serviceKinds[item.kind].label} · {item.scene.project_name||'未指定项目'}</p></CardHeader><CardContent className="flex flex-col gap-lg"><p className="spatial-service-description">{item.scene.description||'固定版本空间服务'}</p><div className="flex flex-wrap items-center justify-between gap-sm text-label-small text-muted-foreground"><span title={item.release.id}>ver: {item.release.id.slice(-8)}</span><time dateTime={item.release.created_at}>{item.release.created_at.slice(0,10)}</time></div><div className="flex flex-wrap items-center justify-end gap-sm"><Button size="xl" variant={item.kind==='query'&&item.available?'default':'secondary'} onClick={()=>setSelected(item.id)}>{item.kind==='query'?'查看接入':'服务详情'}</Button><ServiceAction item={item}/></div></CardContent></Card>;})}{!visible.length&&<div className="scene-catalog-empty"><Globe size={28}/><h2 className="text-heading-3">{items.length?'没有匹配的服务':'暂无已授权的空间服务'}</h2><p className="text-body-small text-muted-foreground">{items.length?'调整搜索关键词、服务类型或状态后重试。':'请联系场景管理员发布服务并分配使用权限。'}</p>{items.length>0&&<Button size="xl" variant="secondary" onClick={()=>{setQuery('');setKind('all');setState('all');}}>清除筛选</Button>}</div>}</div>}
 </div><ServiceDetail key={detail?.id||'closed'} item={detail} onClose={()=>setSelected('')}/></main>;
}
