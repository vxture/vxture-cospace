import React,{useState} from 'react';
import {Badge,Button,StatusBadge,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DropdownMenu,DropdownMenuTrigger,DropdownMenuContent,DropdownMenuItem,Table,TableHeader,TableRow,TableHead,TableBody,TableCell} from '@vxture/design-system';
import {Database,Files,ListBullets,FileArrowUp,CheckCircle,Circle,DotsThreeVertical,Info,ArrowRight,MapPin} from '@phosphor-icons/react';
import {InputRegistration} from './input-registration';
import {InputDetails} from './input-details';
import {InputPreview} from './input-preview';
import {inputFormat} from './input-format';
import {recordLink} from './record-navigation';
import {appNavigate} from './app-router';
export type BuildMaterial={registered_at?:string;registered_at_estimated?:boolean;id:string;label:string;format:string;input_frames:number;used_frames:number;point_count?:number;unit?:string;frame_id?:string;axes?:string[];verified_image_members?:number;verified_messages?:number;lifecycle_state?:string;cloud_sha256?:string;snapshot_sha256?:string;tracking_sha256?:string};
export function BuildMaterials({endpoint,space,items,selectedId,locked,onRegistered,onNext}:{endpoint:string;space:string;items:BuildMaterial[];selectedId?:string;locked:boolean;onRegistered:(id:string)=>void;onNext:()=>void}){
 const [opened,setOpened]=useState<{item:BuildMaterial;mode:'details'|'original'}|null>(null);
 const selected=items.find(i=>i.id===selectedId);
 const select=(item:BuildMaterial)=>appNavigate(recordLink('build',{tab:'tasks',input:item.id}));
 const requirements=selected?selected.format==='ply_pointcloud'?[
  {name:'空间几何',detail:selected.point_count!==undefined?`${selected.point_count.toLocaleString()} 点 · PLY`:'PLY 点云',present:true},
  {name:'坐标与单位',detail:`${selected.frame_id||'坐标基准待补充'} · ${selected.unit||'单位待补充'}`,present:!!selected.frame_id&&selected.unit==='m'},
  {name:'来源清单',detail:'登记快照与来源摘要',present:!!(selected.cloud_sha256||selected.snapshot_sha256)},
 ]:selected.format==='nyu_rgbd_with_existing_poses'?[
  {name:'彩色与深度图像',detail:`${selected.verified_image_members??0} 个已核对图像成员`,present:!!selected.verified_image_members},
  {name:'匹配轨迹',detail:`${selected.used_frames} 帧已有位姿`,present:selected.used_frames>0},
  {name:'来源清单',detail:'封存快照与轨迹引用',present:!!selected.snapshot_sha256},
 ]:[
  {name:'激光采集样本',detail:`${selected.input_frames} 帧 · ${selected.verified_messages??0} 条已核对消息`,present:selected.input_frames>0},
  {name:'时序与坐标声明',detail:selected.format==='ros1_lidar_multiframe_icp'?'多帧时序及一致坐标系需在下一步预检':'首帧与局部坐标声明需在下一步预检',present:false},
  {name:'来源清单',detail:'封存日志与样本快照',present:!!selected.snapshot_sha256},
 ]:[];
 return <div className="build-materials">
  <section className="material-current" aria-label="本次构建资料"><header className="material-section-heading"><Files size={24}/><div className="material-library-heading-copy"><div><h4>本次构建资料</h4><StatusBadge tone={locked?'info':'neutral'}>{locked?'已固化':'未固化'}</StatusBadge></div><p className="material-note material-guidance"><Info size={14}/>{locked?'构建前可添加、更换或取消选用资料；构建后，本次采用的资料不可更换，如需调整，请新建构建。':'一次构建采用一份资料包，点云、图像与轨迹按路线在包内配套。'}{!locked&&' 完整性将在检查整理中核验。'}</p></div></header>
   {selected?<><div className="material-selection"><div><strong>{selected.label}</strong><span>{inputFormat(selected.format)}</span></div></div><div className="material-requirements">{requirements.map(r=><div key={r.name}>{r.present?<CheckCircle size={16}/>:<Circle size={16}/>}<div><strong>{r.name}</strong><span>{r.detail}</span></div><span>{r.present?'已提供':'待核验'}</span></div>)}</div></>:<div className="material-empty"><FileArrowUp size={24}/><strong>选择本次构建的资料包</strong><span>从下方场景资料中选用，或上传新资料。</span></div>}
  </section>
  <section className="material-library" aria-label="场景资料清单"><header className="material-section-heading material-library-heading"><ListBullets size={24}/><div className="material-library-heading-copy"><div><h4>场景资料清单</h4><Badge variant="outline">{items.length}</Badge></div><p className="material-note material-guidance"><Info size={14}/>{locked?'这里展示场景已登记资料，标识本次采用项；其他资料可用于新建构建，不改变本次输入。':'添加资料将登记到当前场景；选用后用于本次构建，构建前可更换或取消。'}</p></div>{!locked&&<InputRegistration endpoint={endpoint} spaceId={space} triggerLabel="添加资料" triggerIcon onRegistered={id=>onRegistered(id)}/>}</header>
   <Table><TableHeader><TableRow><TableHead>序号</TableHead><TableHead>资料名称</TableHead><TableHead>格式</TableHead><TableHead>内容规模</TableHead><TableHead>登记时间</TableHead><TableHead>使用状态</TableHead><TableHead className="material-actions-head">操作</TableHead></TableRow></TableHeader><TableBody>{items.map((item,index)=><TableRow key={item.id} data-selected={item.id===selectedId}><TableCell>{index+1}</TableCell><TableCell className="material-title-cell"><div className="material-name"><Database size={16}/><div><strong>{item.label}</strong><span>{item.id}</span></div></div></TableCell><TableCell>{item.format==='ply_pointcloud'?'PLY':item.format==='nyu_rgbd_with_existing_poses'?'RGB-D':'ROS1'}</TableCell><TableCell>{item.point_count!==undefined?`${item.point_count.toLocaleString()} 点`:`${item.input_frames} 帧`}</TableCell><TableCell>{item.registered_at?new Date(item.registered_at).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'未记录'}{item.registered_at_estimated&&<small className="material-estimate">估算</small>}</TableCell><TableCell><StatusBadge tone={item.id===selectedId?'info':'neutral'}>{item.id===selectedId?'本次采用':item.lifecycle_state==='disabled'?'已停用':item.lifecycle_state==='archived'?'已归档':'可选用'}</StatusBadge></TableCell><TableCell><div className="material-row-actions"><Button variant="ghost" size="sm" onClick={()=>setOpened({item,mode:'original'})}>原始资料</Button>{!locked&&item.id!==selectedId&&<Button variant="secondary" size="sm" disabled={!!item.lifecycle_state&&item.lifecycle_state!=='active'} onClick={()=>select(item)}>选用</Button>}<DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="sm" className="material-more" aria-label={`${item.label}更多操作`}><DotsThreeVertical size={24}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={()=>setOpened({item,mode:'details'})}>资料详情与检查记录</DropdownMenuItem>{locked&&<DropdownMenuItem disabled={!!item.lifecycle_state&&item.lifecycle_state!=='active'} onSelect={()=>select(item)}>基于此资料新建构建</DropdownMenuItem>}{!locked&&item.id===selectedId&&<DropdownMenuItem onSelect={()=>appNavigate(recordLink('build',{tab:'tasks'}))}>取消本次选用</DropdownMenuItem>}</DropdownMenuContent></DropdownMenu></div></TableCell></TableRow>)}</TableBody></Table>{!items.length&&<p className="material-empty">暂无场景资料，请添加资料。</p>}
  </section>
  <details className="material-support"><summary><MapPin size={16}/>辅助资料需求<span>按构建路线提供</span></summary><div><p>已有点云需要坐标基准、单位和来源；RGB-D 需要配套图像与已有轨迹；多帧激光需要时序与坐标系声明。这些配套内容随资料包登记。</p><p>传感器标定、控制点／测量基准、BIM／CAD、语义标注可作为后续构建与验收的辅助资料。独立上传、角色关联和参与构建尚未接入，当前不会将其计入就绪状态。</p></div></details>
  <div className="build-stage-footer"><span>{locked?'构建后资料不可更换 · 可查看检查记录':selected?'已选择 1 份资料包 · 下一步核验完整性':'请选择一份资料包后继续'}</span><Button disabled={!selected} onClick={onNext}>检查整理<ArrowRight size={16}/></Button></div>
  <Dialog open={!!opened} onOpenChange={v=>{if(!v)setOpened(null);}}><DialogContent className="material-detail-dialog"><DialogHeader><DialogTitle>{opened?.mode==='original'?'原始资料':'资料详情与检查记录'}</DialogTitle><DialogDescription>{opened?.item.label}</DialogDescription></DialogHeader>{opened&&(opened.mode==='original'?<InputPreview endpoint={endpoint} space={space} input={opened.item}/>:<InputDetails endpoint={endpoint} identity={opened.item.id} lifecycleState={opened.item.lifecycle_state}/>)}</DialogContent></Dialog>
 </div>;
}
