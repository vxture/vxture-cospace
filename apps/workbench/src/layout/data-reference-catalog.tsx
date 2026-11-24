import React,{useEffect,useState} from 'react';
import {Button,Drawer,Input,Table,TableBody,TableCell,TableHead,TableHeader,TableRow,StatusBadge,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem} from '@vxture/design-system';
import {ArrowClockwise,DotsThreeVertical,LinkSimple,MagnifyingGlass,Info} from '@phosphor-icons/react';
import {WorkspaceContent} from './workspace-content';
import {WorkspaceHeading} from './workspace-frame';
import {DataNavigation} from './data-navigation';
import {ProjectPicker} from './data-project-picker';
import {dataRequest} from './data-project-client';
import {dataCatalogHref} from './data-catalog-contract';
import {DataReferenceDetails} from './data-reference-details';
import {DataLineagePanel} from './data-lineage-panel';
import {appLocation,appNavigate} from './app-router';
import {parseSharingReport,sharingStatus,type SharingReport,type ResourceUse} from './data-sharing-contract';

export function DataReferenceCatalog({workspace}:{workspace:string}){
 const params=new URLSearchParams(appLocation().split('?')[1]||''),project=params.get('project')||'',search=params.get('search')||'',offset=/^\d+$/.test(params.get('offset')||'')?Number(params.get('offset')):0;
 const [draft,setDraft]=useState(search),[saved,setSaved]=useState<{key:string;report:SharingReport}|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[generation,setGeneration]=useState(0),[selected,setSelected]=useState<ResourceUse|null>(null);
 const key=JSON.stringify([workspace,project,search,offset,generation]),report=saved?.key===key?saved.report:null;
 function navigate(values:Record<string,string>){appNavigate(dataCatalogHref({category:'uses',project,search,offset:'0',...values}));}
 useEffect(()=>setDraft(search),[search]);
 useEffect(()=>{const c=new AbortController();setError('');setSelected(null);if(!project){setLoading(false);return;}setLoading(true);
  void dataRequest('/api/data-sharing?'+new URLSearchParams({view:'uses',project_id:project,search,offset:String(offset),limit:'20'}),c.signal).then(v=>parseSharingReport(v,{workspace,view:'uses',project})).then(v=>{if(!c.signal.aborted)setSaved({key,report:v});}).catch(e=>{if(!c.signal.aborted)setError(e.message);}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();
 },[workspace,project,search,offset,generation]);
 const refresh=()=>setGeneration(v=>v+1);
 return <div className="shared-support-layout" data-layout="management"><DataNavigation category="uses"/><section className="shared-data-catalog workspace-content-viewport" aria-label="数据引用记录"><WorkspaceContent className="data-resource-catalog"><WorkspaceHeading icon={LinkSimple} title="引用记录" description="按项目核对固定版本、用途与当前授权，保留已解除的历史记录。" actions={<Button variant="ghost" size="icon-sm" className="data-catalog-icon-button" aria-label="刷新引用记录" disabled={loading} onClick={refresh}><ArrowClockwise size={16}/></Button>}/>
 <div className="data-catalog-toolbar"><span className="data-resource-count">{report?`共 ${report.total} 项`:'— 项'}</span><ProjectPicker workspace={workspace} value={project} allowAll onChange={value=>navigate({project:value,search:''})}/><form onSubmit={e=>{e.preventDefault();navigate({search:draft});}}><Input aria-label="搜索引用记录" placeholder="搜索数据、用途或关联场景" value={draft} maxLength={100} onChange={e=>setDraft(e.target.value)}/><Button type="submit" variant="outline" size="icon-sm" className="data-catalog-icon-button" aria-label="搜索引用记录"><MagnifyingGlass size={16}/></Button></form></div>
 {!project&&<p>请选择项目查看引用记录。</p>}{loading&&<p role="status">正在读取引用记录…</p>}{error&&<div role="alert"><p>{error}</p><Button variant="outline" size="sm" onClick={refresh}>重新读取</Button></div>}
 {report&&<><Table className="data-resource-table"><TableHeader><TableRow><TableHead className="data-resource-index">序号</TableHead><TableHead>数据 / 固定版本</TableHead><TableHead>关联范围</TableHead><TableHead>引用用途</TableHead><TableHead>引用 / 授权状态</TableHead><TableHead className="data-resource-actions">操作</TableHead></TableRow></TableHeader><TableBody>{(report.items as ResourceUse[]).map((u,index)=><TableRow key={u.id}><TableCell className="data-resource-index">{offset+index+1}</TableCell><TableCell><div className="data-resource-name"><button onClick={()=>setSelected(u)}>{u.snapshot.label}</button></div><small className="data-resource-secondary">{u.version_id.slice(0,12)}</small></TableCell><TableCell>{u.space_name||'项目级'}</TableCell><TableCell>{u.purpose}</TableCell><TableCell><StatusBadge tone={u.access_status==='active'?'neutral':'warning'}>{sharingStatus[u.access_status]}</StatusBadge></TableCell><TableCell className="data-resource-actions"><DropdownMenu><DropdownMenuTrigger asChild><Button size="icon-sm" className="data-catalog-icon-button" variant="ghost" aria-label={u.snapshot.label+'引用操作'}><DotsThreeVertical size={24}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={()=>setSelected(u)}><Info size={16}/>查看引用详情</DropdownMenuItem></DropdownMenuContent></DropdownMenu></TableCell></TableRow>)}</TableBody></Table>{!report.items.length&&<p>当前范围没有引用记录。</p>}<div className="data-resource-pagination"><span>共 {report.total} 项</span><Button size="sm" variant="outline" disabled={!offset} onClick={()=>navigate({offset:String(Math.max(0,offset-20))})}>上一页</Button><Button size="sm" variant="outline" disabled={report.next_offset===null} onClick={()=>navigate({offset:String(report.next_offset)})}>下一页</Button></div></>}
 {selected?.project_id===project&&<Drawer open side="right" width="lg" title="引用详情" className="data-management-drawer" onClose={()=>setSelected(null)}><div className="data-project-form"><DataReferenceDetails uses={[selected]} onChanged={refresh}/><DataLineagePanel workspace={workspace} resource={selected.resource_id} project={project}/></div></Drawer>}
 </WorkspaceContent></section></div>;
}
