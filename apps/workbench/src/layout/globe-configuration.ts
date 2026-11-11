import {useEffect,useState} from 'react';
import {SDK_VERSION,CESIUM_VERSION,type GlobeConfiguration} from '@vxture/globe';
import {businessEndpoint} from './business-endpoint';
export type RuntimeGlobeConfiguration=GlobeConfiguration&{embedOrigins:string[];sdkVersion:string;cesiumVersion:string};
export function useGlobeConfiguration(){
 const [configuration,setConfiguration]=useState<RuntimeGlobeConfiguration|null>(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[loading,setLoading]=useState(true);
 const retry=()=>setRevision(value=>value+1);
 useEffect(()=>{window.addEventListener('cospace:session-confirmed',retry);return()=>window.removeEventListener('cospace:session-confirmed',retry);},[]);
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');fetch(`${businessEndpoint}/api/globe/config`,{cache:'no-store',signal:controller.signal}).then(async response=>{if(!response.ok)throw Error(response.status===401?'请恢复登录后重试。':'地球配置服务暂不可用，请重试。');const value=await response.json();if(value.profile!=='vxture.globe-config/0.1'||value.sdkVersion!==SDK_VERSION||value.cesiumVersion!==CESIUM_VERSION||!Array.isArray(value.embedOrigins))throw Error('地球前后端版本不一致，请更新服务后重试。');if(!controller.signal.aborted)setConfiguration(previous=>JSON.stringify(previous)===JSON.stringify(value)?previous:value);}).catch(error=>{if(!controller.signal.aborted)setError(error.message||'地球配置暂不可用，请重试。');}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[revision]);
 return {configuration,error,loading,retry};
}
