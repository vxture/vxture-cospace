import React,{useEffect,useState} from 'react';
import {ArrowRight,Info} from '@phosphor-icons/react';
import {Button} from '@vxture/design-system';
import {businessEndpoint} from './business-endpoint';
import {recordLink} from './record-navigation';
import {CoordinateReadiness,type AxisReadiness} from './coordinate-readiness';

type Source={profile:string;space_id:string;candidate_id:string;input_id:string|null;frame_id:string;registration_readiness:AxisReadiness;can_manage_input:boolean};
export function RegistrationSourceRecovery({spaceId,candidateId}:{spaceId:string;candidateId:string}){
 const [data,setData]=useState<Source|null>(null),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 useEffect(()=>{const abort=new AbortController();setData(null);setError('');
  fetch(businessEndpoint+'/api/scene-registrations/source?'+new URLSearchParams({space_id:spaceId,candidate_id:candidateId}),{signal:abort.signal,cache:'no-store'}).then(async response=>{
   if(!response.ok)throw Error('来源诊断暂不可读，请重试或联系场景管理员。');const value:Source=await response.json();
   if(value.profile!=='cospace.registration-source/0.1'||value.space_id!==spaceId||value.candidate_id!==candidateId||!value.registration_readiness||value.input_id&&!/^input-[a-f0-9]{16}$/.test(value.input_id))throw Error('来源诊断与当前模型不一致。');
   if(!abort.signal.aborted)setData(value);
  }).catch(reason=>{if(!abort.signal.aborted)setError(reason.message);});return()=>abort.abort();
 },[spaceId,candidateId,refresh]);
 return <section className="flex min-w-0 flex-col gap-lg rounded-md border border-border p-lg" aria-label="配准来源处理">
  <div className="flex items-center gap-sm"><Info size={20}/><h3 className="text-heading-small">补齐模型坐标定义</h3></div>
  {!data&&!error&&<output>正在核对固定模型与来源资料…</output>}
  {error&&<div className="flex flex-wrap items-center gap-sm" role="alert"><p>{error}</p><Button size="sm" variant="outline" onClick={()=>setRefresh(n=>n+1)}>重试来源诊断</Button></div>}
  {data&&<><CoordinateReadiness value={data.registration_readiness}/><ol className="list-decimal space-y-sm pl-lg text-body-small">
   <li>核对原始资料中的单位、轴向和坐标约定；系统兼容明确的方向别名，无法确定的方向需由资料提供者补充。</li>
   <li>{data.input_id?'在来源资料中修订坐标说明，填写来源依据；保存后重新执行预检。':'此模型没有可追溯的登记输入，请导入带明确坐标声明的资料。'}</li>
   <li>使用修订后的资料新建构建，再回到地图配准选择新模型。</li>
  </ol><p className="text-label-small text-muted-foreground">修订不改变原点云数值。若实际需要翻轴、旋转或单位换算，应先转换数据；历史模型与已发布版本继续使用原声明。</p>
  {data.can_manage_input?<div className="flex flex-wrap gap-sm"><Button asChild size="sm"><a href={recordLink('data',{space:spaceId,tab:'inputs',...(data.input_id?{input:data.input_id}:{})})}>{data.input_id?'查看并修订来源资料':'前往资料管理'}<ArrowRight size={16}/></a></Button>{data.input_id&&<Button asChild size="sm" variant="outline"><a href={recordLink('build',{space:spaceId,input:data.input_id})}>前往构建中心</a></Button>}</div>:<p className="text-body-small">请由具备资料管理权限的场景成员补齐定义并构建新模型。</p>}</>}
 </section>;
}
