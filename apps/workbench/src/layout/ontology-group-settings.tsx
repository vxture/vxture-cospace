import React,{useState} from 'react';
import {OntologyGroupConfiguration,parseGroupConfiguration,type GroupConfigurationClient} from '@vxture/ontology-ui/group-configuration';
import {businessEndpoint} from './business-endpoint';
import {usePlatformSession} from './platform-auth';
import {useUnsavedNavigation} from './unsaved-navigation';
const path=businessEndpoint+'/api/ontology-configuration/groups';
const messages:Record<string,string>={ontology_group_revision_changed:'配置已被其他人修改。请取消编辑并刷新后重新核对。',ontology_group_name_exists:'此作用域内已有同名分组。',ontology_group_request_conflict:'提交标识发生冲突，请重新打开配置核对。',ontology_group_preset_name_fixed:'预置分组名称不能修改。',ontology_group_invalid_request:'请检查名称、排序值和修改原因。'};
async function result(response:Response){if(!response.ok){let detail='';try{detail=(await response.json()).detail;}catch{}throw Error(messages[detail]||(response.status===403?'当前身份无权管理本体分组配置。':response.status===401?'请登录后读取配置。':'分组配置暂不可用，请稍后重试。'));}return parseGroupConfiguration(await response.json());}
const client:GroupConfigurationClient={load:async signal=>result(await fetch(path,{signal,cache:'no-store'})),save:async(change,signal)=>result(await fetch(path,{method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(change)}))};
function Content(){const [dirty,setDirty]=useState(false);useUnsavedNavigation(dirty,'本体分组配置');return <OntologyGroupConfiguration client={client} onDirtyChange={setDirty}/>;}
export function OntologyGroupSettings(){const session=usePlatformSession();return <Content key={[session?.user?.subject,session?.user?.org_id,session?.user?.workspace_id].join('/')}/>;}
