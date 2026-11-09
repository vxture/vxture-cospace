export type Point=[number,number];
export type AmapMarker={on:(event:string,callback:()=>void)=>void;setMap:(map:AmapMap|null)=>void;setContent:(content:HTMLElement)=>void};
export type AmapMap={destroy:()=>void;setFeatures:(features:string[])=>void;setStatus:(status:{scrollWheel:boolean})=>void;setMapStyle:(style:string)=>void;setZoomAndCenter:(zoom:number,point:Point)=>void;setFitView:(markers?:AmapMarker[],immediately?:boolean,padding?:number[],maxZoom?:number)=>void;zoomIn:()=>void;zoomOut:()=>void;on:(event:string,callback:()=>void)=>void;off:(event:string,callback:()=>void)=>void};
export type AmapSDK={Map:new(host:HTMLElement,options:Record<string,unknown>)=>AmapMap;Marker:new(options:Record<string,unknown>)=>AmapMarker;convertFrom:(points:Point[],type:string,callback:(status:string,result:{locations?:{getLng:()=>number;getLat:()=>number}[]})=>void)=>void};
declare global{interface Window{AMap?:AmapSDK;_AMapSecurityConfig?:{serviceHost:string}}}
let pending:Promise<AmapSDK>|undefined;
export async function loadAmap():Promise<AmapSDK>{
 if(window.AMap)return window.AMap;
 if(pending)return pending;
 pending=(async()=>{
  const response=await fetch('/api/map/config',{cache:'no-store'});
  if(!response.ok)throw Error('暂时无法读取地图配置，请重试。');
  const config=await response.json();
  if(!config.enabled)throw Error('高德地图尚未配置，请联系管理员完成接入。');
  if(!/^[a-f0-9]{32}$/i.test(config.key)||config.service_host!=='/_AMapService')throw Error('地图配置无法识别。');
  window._AMapSecurityConfig={serviceHost:location.origin+config.service_host};
  return await new Promise<AmapSDK>((resolve,reject)=>{
   const script=document.createElement('script');script.src='https://webapi.amap.com/maps?v=2.0&key='+encodeURIComponent(config.key);script.async=true;
   const timeout=window.setTimeout(()=>{script.remove();reject(Error('地图加载超时，请检查网络后重试。'));},20000);
   script.onload=()=>{clearTimeout(timeout);if(window.AMap)resolve(window.AMap);else{script.remove();reject(Error('高德地图初始化失败，请重试。'));}};
   script.onerror=()=>{clearTimeout(timeout);script.remove();reject(Error('高德地图加载失败，请检查网络后重试。'));};
   document.head.append(script);
  });
 })();
 try{return await pending;}catch(error){pending=undefined;throw error;}
}

// Convert only the display copy. Original surveyed coordinates remain untouched.
export async function displayPoints(_sdk:AmapSDK,locations:{longitude:number;latitude:number;crs:'WGS84'|'GCJ02'}[]):Promise<Point[]>{
 const valid=locations.every(p=>Number.isFinite(p.longitude)&&Number.isFinite(p.latitude)&&Math.abs(p.longitude)<=180&&Math.abs(p.latitude)<=90&&['WGS84','GCJ02'].includes(p.crs));
 if(!valid)throw Error('场景坐标格式无效，请核对位置登记。');
 const result:Point[]=locations.map(p=>[p.longitude,p.latitude]);
 const indices=locations.flatMap((p,i)=>p.crs==='WGS84'?[i]:[]);
 for(let start=0;start<indices.length;start+=40){
  const batch=indices.slice(start,start+40);
  // Match the official JS API convertFrom protocol, through our authenticated proxy.
  const response=await fetch('/_AMapService/v3/assistant/coordinate/convert?'+new URLSearchParams({s:'rsv3',locations:batch.map(i=>result[i].join(',')).join(';'),coordsys:'gps',output:'json'}),{signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error('坐标转换暂不可用，请重试。');
  const data=await response.json();
  const converted:Point[]=typeof data.locations==='string'?data.locations.split(';').map((p:string)=>p.split(',').map(Number) as Point):[];
  if(data.status!=='1'||converted.length!==batch.length||converted.some(p=>p.length!==2||!p.every(Number.isFinite)))throw Error('坐标转换失败，请重试。');
  batch.forEach((index,i)=>{result[index]=converted[i];});
 }
 return result;
}
