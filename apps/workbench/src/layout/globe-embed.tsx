import React,{useEffect,useRef,useState} from 'react';
import {bindingKey,GLOBE_PROTOCOL,parseEmbedCommand,type GlobeController,type GlobeSelection} from '@vxture/globe';
import {SceneGlobe} from './scene-globe';
import {businessEndpoint} from './business-endpoint';
import type {SceneSpace} from './scene-directory';
import {useGlobeConfiguration} from './globe-configuration';

// Each viewer is bound to one explicitly selected, authorized publication. No latest fallback.
export function GlobeEmbed(){
 const params=new URLSearchParams(location.search),spaceId=params.get('space')||'',publicationId=params.get('publication')||'',parentOrigin=params.get('parent_origin')||location.origin;
 const {configuration,error:configurationError}=useGlobeConfiguration();
 const [scene,setScene]=useState<SceneSpace|null>(null),[error,setError]=useState('');
 const api=useRef<GlobeController|null>(null);
 const binding={spaceId,publicationId};
 function send(value:object){if(configuration?.embedOrigins.includes(parentOrigin)&&window.parent!==window)window.parent.postMessage({protocol:GLOBE_PROTOCOL,...value},parentOrigin);}
 useEffect(()=>{
  const controller=new AbortController();
  if(!spaceId||!publicationId){setError('请指定场景和固定发布版本。');return;}
  const load=async()=>{
   const directory=await fetch(`${businessEndpoint}/api/spaces`,{cache:'no-store',signal:controller.signal});if(!directory.ok)throw Error();
   const body=await directory.json(),found:SceneSpace|undefined=body.spaces?.find((item:SceneSpace)=>item.id===spaceId);
   const publication=found?.publications?.find(item=>item.id===publicationId);
   if(!found||!publication||['retired','paused','withdrawn'].includes(publication.lifecycle_state||''))throw Error();
   // The server checks current publication lifecycle and scene.preview permission again.
   const access=await fetch(`${businessEndpoint}/publications/${encodeURIComponent(publicationId)}/api/preview`,{cache:'no-store',signal:controller.signal});if(!access.ok)throw Error();
   if(!controller.signal.aborted)setScene({...found,publications:[publication]});
  };
  load().catch(()=>{if(!controller.signal.aborted)setError('该场景或固定发布版本当前不可访问。');});
  return()=>controller.abort();
 },[spaceId,publicationId]);
 useEffect(()=>{
  if(!configuration?.embedOrigins.includes(parentOrigin)||!scene)return;
  const receive=(event:MessageEvent)=>{
   if(event.origin!==parentOrigin||event.source!==window.parent)return;
   const message=parseEmbedCommand(event.data);if(!message)return;
   try{
    if(!api.current)throw Error();
    if(message.command.type==='focus'&&bindingKey(message.command.binding)!==bindingKey(binding))throw Error();
    api.current.command(message.command);send({type:'ack',requestId:message.requestId});
   }catch{send({type:'error',requestId:message.requestId,code:'command_unavailable'});}
  };
  window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);
 },[configuration,scene,parentOrigin,spaceId,publicationId]);
 const failure=error||configurationError||(configuration&&!configuration.embedOrigins.includes(parentOrigin)?'嵌入来源未授权。':'');
 if(failure)return <main className="flex h-dvh items-center justify-center bg-background text-foreground" role="alert">{failure}</main>;
 if(!scene||!configuration)return <main className="h-dvh bg-background text-foreground" role="status">正在校验固定发布版本…</main>;
 return <div className="relative flex h-dvh flex-col overflow-hidden"><SceneGlobe embedded spaces={[scene]} publicationId={publicationId} loading={false} error="" onBack={()=>{}} onRefresh={()=>location.reload()} onViewChange={()=>{}} onController={controller=>{api.current=controller;if(controller)send({type:'ready',binding});}} onSelection={(selection:GlobeSelection|null)=>send({type:'selection',selection})}/></div>;
}
