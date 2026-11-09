import type {PreviewGeometry} from './geometry-preview-data';

/** Camera framing only: keep all geometry, focus on the main observed cluster. */
export function scanFocus(data:PreviewGeometry){
 const center=[0,1,2].map(axis=>data.points.map(p=>p[axis]).sort((a,b)=>a-b)[Math.floor(data.points.length/2)]);
 const distances=data.points.map(p=>Math.hypot(...p.map((v,i)=>v-center[i]))).sort((a,b)=>a-b);
 return {center,radius:Math.max(distances[Math.floor((distances.length-1)*.9)],.01)};
}

/** Presentation order only. Static files contain no acquisition time or robot pose. */
export function scanOrder(data:PreviewGeometry){
 const nyu=data.axes.join('/')==='right/down/forward',horizontal=nyu?2:1;
 const {center}=scanFocus(data);
 const angle=(p:number[])=>Math.atan2(p[horizontal]-center[horizontal],p[0]-center[0])+Math.PI;
 const indices=data.points.map((_,i)=>i).sort((a,b)=>angle(data.points[a])-angle(data.points[b])||a-b);
 return {...data,points:indices.map(i=>data.points[i]),colors:indices.map(i=>data.colors[i])};
}

export function buildScanHref(space:string,job:string,input:string){
 return `/build?${new URLSearchParams({screen:'build',space,job,input,tab:'flow'})}`;
}
