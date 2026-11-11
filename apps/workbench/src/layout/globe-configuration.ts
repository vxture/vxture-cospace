import {useEffect,useState} from 'react';
import type {GlobeConfiguration} from '@vxture/globe';
import {businessEndpoint} from './business-endpoint';
export type RuntimeGlobeConfiguration=GlobeConfiguration&{embedOrigins:string[];sdkVersion:string;cesiumVersion:string};
export function useGlobeConfiguration(){
 const [configuration,setConfiguration]=useState<RuntimeGlobeConfiguration|null>(null),[error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();fetch(`${businessEndpoint}/api/globe/config`,{cache:'no-store',signal:controller.signal}).then(async response=>{if(!response.ok)throw Error();const value=await response.json();if(value.profile!=='vxture.globe-config/0.1'||value.sdkVersion!=='0.1.0'||value.cesiumVersion!=='1.147.0'||!Array.isArray(value.embedOrigins))throw Error();if(!controller.signal.aborted)setConfiguration(value);}).catch(()=>{if(!controller.signal.aborted)setError('地球配置暂不可用，请重新打开。');});return()=>controller.abort();},[]);
 return {configuration,error};
}
