import {PublicHeaderTools} from './public-header-tools';

import {PlatformHeader as ShellHeader} from './platform-header';
import React from 'react';
import {ShellHeaderMark,ShellHeaderDivider,ShellProductTitle,ShellLegalFooter} from '@vxture/design-system';
import {PlatformProductBrand} from './product-brand';

// Product illustration only. It does not represent a captured or published space.
function SpatialIllustration({expanded=false}:{expanded?:boolean}){
 const point=(x:number,y:number,z=0)=>[365+(x-y)*.86,140+(x+y)*.43-z];
 const points=(vertices:number[][])=>vertices.map(v=>point(v[0],v[1],v[2]||0).join(',')).join(' ');
 const line=(a:number[],b:number[])=>`M${points([a])}L${points([b])}`;
 const box=(x:number,y:number,w:number,d:number,h:number)=><g>
  <polygon points={points([[x,y],[x+w,y],[x+w,y,h],[x,y,h]])} className="home-device-front"/>
  <polygon points={points([[x+w,y],[x+w,y+d],[x+w,y+d,h],[x+w,y,h]])} className="home-device-side"/>
  <polygon points={points([[x,y,h],[x+w,y,h],[x+w,y+d,h],[x,y+d,h]])} className="home-device-top"/>
  <path d={line([x+5,y,10],[x+w-5,y,10])+line([x+5,y,17],[x+w-5,y,17])} opacity=".25"/>
 </g>;
 let seed=17;const random=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
 const samples=Array.from({length:580},(_,i)=>{
  const wall=i%3;const x=wall===0?random()*330:wall===1?0:random()*330;
  const y=wall===1?random()*245:wall===0?0:random()*245;
  const [cx,cy]=point(x,y,wall===2?0:random()*70);
  return <circle key={i} cx={cx} cy={cy} r={random()*.7+.35} opacity={random()*.4+.15}/>;
 });
 return <svg className="home-space-art" viewBox="0 0 760 430" fill="none" aria-hidden="true">
  <defs><radialGradient id="home-floor"><stop stopColor="var(--primary)" stopOpacity=".09"/><stop offset="1" stopColor="var(--primary)" stopOpacity="0"/></radialGradient></defs>
  <ellipse cx="380" cy="303" rx="310" ry="114" fill="url(#home-floor)"/>
  {expanded&&<g className="home-map-context">
   {Array.from({length:25},(_,i)=><path key={i} d={line([-250+i*35,-210],[-250+i*35,500])+line([-250,-210+i*30],[590,-210+i*30])} opacity=".35"/>)}
   {[[-185,15,155,190],[365,-75,180,170],[220,280,200,145],[-65,-160,230,125]].map(([x,y,w,d],i)=><g key={i}>
    <polygon points={points([[x,y],[x+w,y],[x+w,y+d],[x,y+d]])}/>
    <path d={line([x,y],[x,y,45])+line([x,y,45],[x+w,y,45])+line([x,y,45],[x,y+d,45])+line([x+w,y,45],[x+w,y])+line([x,y+d,45],[x,y+d])}/>
    <path d={line([x+w*.56,y],[x+w*.56,y+d*.4])+line([x+w*.56,y+d*.65],[x+w*.56,y+d])} opacity=".6"/>
   </g>)}
  </g>}
  <g className="home-map-grid">{Array.from({length:15},(_,i)=><path key={i} d={line([-70+i*35,-65],[-70+i*35,320])+line([-70,-65+i*30],[420,-65+i*30])}/>)}</g>
  <polygon points={points([[0,0],[330,0],[330,245],[0,245]])} className="home-map-floor"/>
  <g className="home-map-walls"><polygon points={points([[0,0],[330,0],[330,0,70],[0,0,70]])}/><polygon points={points([[0,0],[0,245],[0,245,70],[0,0,70]])}/></g>
  <g className="home-map-edges"><path d={line([0,245,70],[0,0,70])+line([0,0,70],[330,0,70])}/><path d={line([0,245],[330,245])+line([330,245],[330,0])} opacity=".35"/></g>
  <g className="home-map-partition"><polygon points={points([[190,0],[190,83],[190,83,55],[190,0,55]])}/><polygon points={points([[190,133],[190,245],[190,245,55],[190,133,55]])}/></g>
  <g className="home-map-equipment">{[28,83,138].map(x=><React.Fragment key={x}>{box(x,16,34,30,46)}</React.Fragment>)}{box(22,160,42,47,29)}{box(226,28,63,40,25)}{box(257,164,38,43,49)}</g>
  <g fill="currentColor" className="home-map-points">{samples}</g>
  <path d={line([83,213],[116,180])+line([116,180],[116,108])+line([116,108],[235,108])+line([235,108],[279,137])} className="home-map-route"/>
  {[[116,180],[116,108],[235,108]].map(([x,y],i)=>{const [cx,cy]=point(x,y);return <g key={i}><ellipse cx={cx} cy={cy} rx="8" ry="4" className="home-map-node-halo"/><circle cx={cx} cy={cy} r="2.5" className="home-map-node"/></g>;})}
  <g className="home-map-focus"><ellipse cx={point(279,137)[0]} cy={point(279,137)[1]} rx="27" ry="13.5"/><ellipse cx={point(279,137)[0]} cy={point(279,137)[1]} rx="16" ry="8"/><path d={line([279,137],[279,137,35])}/><circle cx={point(279,137,35)[0]} cy={point(279,137,35)[1]} r="4"/></g>
 </svg>;
}

// One composed indoor/outdoor site; the viewport crops a larger scene.
function SiteSceneBackground(){
 const p=(x:number,y:number,z=0)=>[690+(x-y)*.9,90+(x+y)*.45-z];
 const pts=(v:number[][])=>v.map(a=>p(a[0],a[1],a[2]||0).join(',')).join(' ');
 const path=(v:number[][])=>v.map((a,i)=>(i?'L':'M')+p(a[0],a[1],a[2]||0).join(',')).join(' ');
 const floor=(x:number,y:number,w:number,d:number,cls:string)=><polygon className={cls} points={pts([[x,y],[x+w,y],[x+w,y+d],[x,y+d]])}/>;
 const wall=(x:number,y:number,x2:number,y2:number,h=62)=><polygon className="site-wall" points={pts([[x,y],[x2,y2],[x2,y2,h],[x,y,h]])}/>;
 const block=(x:number,y:number,w:number,d:number,h:number)=><g className="site-device">
  <polygon className="site-device-front" points={pts([[x,y],[x+w,y],[x+w,y,h],[x,y,h]])}/>
  <polygon className="site-device-side" points={pts([[x+w,y],[x+w,y+d],[x+w,y+d,h],[x+w,y,h]])}/>
  <polygon className="site-device-top" points={pts([[x,y,h],[x+w,y,h],[x+w,y+d,h],[x,y+d,h]])}/>
  <path d={path([[x+5,y,12],[x+w-5,y,12]])}/>
 </g>;
 const route=path([[45,470],[45,350],[260,350],[360,350],[520,350],[650,350],[740,350],[740,180],[740,-40],[565,-40],[410,-180],[160,-180]]);
 return <svg className="home-endless-space home-site-scene" viewBox="0 -160 1600 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true" fill="none">
  <g className="site-ground-grid">{Array.from({length:51},(_,i)=><path key={i} d={path([[-1400+i*70,-1500],[-1400+i*70,2000]])+path([[-1600,-1400+i*70],[2100,-1400+i*70]])}/>)}</g>
  {/* The access road and garden continue beyond the crop, with no site perimeter. */}
  {floor(635,-1500,215,3400,'site-road')}
  <path className="site-road-center" d={path([[742,-1500],[742,2000]])}/>
  {floor(-700,-700,1240,490,'site-garden')}
  {floor(890,-1000,620,2400,'site-garden')}
  <g className="site-walkway"><path d={path([[-700,-170],[570,-170],[570,-55],[635,-55]])}/><path d={path([[850,490],[1300,490]])}/></g>
  {/* An irregular connected building: plant room, corridor, offices and loading bay. */}
  {floor(-400,0,980,650,'site-building')}
  {floor(-400,300,980,100,'site-corridor')}
  {floor(-400,0,360,300,'site-room-floor')}
  {floor(-40,0,340,300,'site-room-floor')}
  {floor(300,0,280,300,'site-workshop-floor')}
  {floor(-400,400,310,250,'site-office-floor')}
  {floor(-90,400,280,250,'site-room-floor')}
  {floor(190,400,390,250,'site-workshop-floor')}
  <g className="site-walls">
   {wall(-400,0,580,0,85)}{wall(-400,0,-400,650,85)}
   {wall(-40,0,-40,300)}{wall(300,0,300,300)}
   {wall(-400,300,-220,300)}{wall(-150,300,105,300)}{wall(175,300,390,300)}{wall(470,300,580,300)}
   {wall(-400,400,-200,400)}{wall(-135,400,0,400)}{wall(70,400,280,400)}{wall(360,400,580,400)}
   {wall(-90,400,-90,650)}{wall(190,400,190,650)}
   {wall(580,0,580,290)}{wall(580,410,580,650)}
  </g>
  <g className="site-equipment">
   {[-330,-250,-170].map(x=><React.Fragment key={x}>{block(x,40,48,42,65)}</React.Fragment>)}
   {block(-325,180,125,65,32)}{block(-145,190,52,55,45)}
   {[15,95,175].map(x=><React.Fragment key={x}>{block(x,45,48,48,72)}</React.Fragment>)}
   {block(35,200,170,50,25)}{block(370,70,120,110,35)}
   {block(350,480,145,65,26)}{block(400,575,65,45,43)}
   {block(-330,480,95,50,24)}{block(-200,555,55,50,24)}
   {block(-30,485,100,52,24)}{block(95,565,48,48,55)}
  </g>
  <g className="site-windows">{[-330,-205,-80,45,170,395].map(x=><path key={x} d={path([[x,0,38],[x+65,0,38],[x+65,0,68],[x,0,68],[x,0,38]])}/>)}</g>
  {floor(580,430,55,180,'site-loading')}
  <g className="site-parking">{[100,185,270,355,440].map(y=><path key={y} d={path([[895,y],[990,y],[990,y+60],[895,y+60]])}/>)}</g>
  {block(910,115,58,100,22)}{block(910,365,58,90,22)}
  <g className="site-trees">{[[-460,-360],[-250,-450],[-40,-345],[170,-470],[365,-320],[1000,-145],[1145,120],[1070,640],[1220,780],[-520,760]].map(([x,y],i)=>{
   const [cx,cy]=p(x,y);return <g key={i}><ellipse cx={cx+8} cy={cy+8} rx="30" ry="15" className="site-tree-shadow"/><path d={path([[x,y],[x,y,36]])}/><ellipse cx={cx} cy={cy-42} rx={23+i%3*5} ry={28+i%3*4} className="site-tree-canopy"/></g>;
  })}</g>
  <g className="site-crossing">{Array.from({length:7},(_,i)=>floor(650+i*26,450,12,65,'site-crossing-stripe'))}</g>
  <g className="site-route"><path className="site-route-underlay" d={route}/><path className="site-route-flow" d={route}/>
   {[[45,470],[360,350],[740,180],[160,-180]].map(([x,y],i)=>{const [cx,cy]=p(x,y);return <g key={i}><ellipse cx={cx} cy={cy} rx="10" ry="5"/><circle cx={cx} cy={cy} r="3"/></g>;})}
  </g>
 </svg>;
}

export function HomeLayout({children,tools,footerTools}:{children:React.ReactNode;tools?:React.ReactNode;footerTools?:React.ReactNode}){
 const panoramic=new URLSearchParams(location.search).get('home')!=='split';
 if(panoramic)return <div className="cospace-home home-panorama bg-background text-foreground" id="login-screen">
  <div className="home-panorama-backdrop" aria-hidden="true"><SiteSceneBackground/></div>
  <ShellHeader className="home-header" height="xl" layout="centered" surface="transparent" leading={<PlatformProductBrand/>} trailing={<PublicHeaderTools/>}/>
  <main className="home-main home-panorama-main">
   <div className="home-content-inner">
   <div className="home-panorama-content">
    <p className="home-panorama-eyebrow">SPATIAL INTELLIGENCE</p>
    <section className="home-entry home-panorama-entry" aria-label="CoSpace 访问入口">{children}</section>
    <div className="home-panorama-message"><p>空间底图建一次　具身智能体共用</p><span>MAP ONCE. SHARE ACROSS AGENTS.</span></div>
   </div>
   </div>
  </main>
  {footerTools&&<div className="home-preview-tools" aria-label="设计验证工具">{footerTools}</div>}<footer className="home-footer public-legal-footer"><div className="home-footer-inner"><span>© 2026 VXTURE · RUYIN</span><nav aria-label="法律信息"><a href="https://vxture.com/zh-CN/legal/terms" target="_blank" rel="noopener noreferrer">服务条款</a><a href="https://vxture.com/zh-CN/legal/privacy" target="_blank" rel="noopener noreferrer">隐私政策</a><a href="https://vxture.com/zh-CN/legal/copyright" target="_blank" rel="noopener noreferrer">版权声明</a></nav></div></footer>
 </div>;
 return <div className="cospace-home bg-background text-foreground" id="login-screen">
  <ShellHeader className="home-header" height="xl" layout="centered" surface="transparent" leading={<PlatformProductBrand/>} trailing={<PublicHeaderTools/>}/>
  <main className="home-main">
   <div className="home-grid">
    <section className="home-visual" aria-label="空间服务产品介绍">
     <div className="home-intro"><p className="home-eyebrow">SPATIAL INTELLIGENCE</p><p className="home-tagline">空间底图建一次　具身智能体共用</p></div>
     <SpatialIllustration/>
     <div className="home-visual-caption" aria-hidden="true"><span className="home-caption-line"/>MAP ONCE. SHARE ACROSS AGENTS.</div>
    </section>
    <section className="home-entry" aria-label="CoSpace 访问入口">{children}</section>
   </div>
  </main>
  {footerTools&&<div className="home-preview-tools" aria-label="设计验证工具">{footerTools}</div>}<footer className="home-footer public-legal-footer"><div className="home-footer-inner"><span>© 2026 VXTURE · RUYIN</span><nav aria-label="法律信息"><a href="https://vxture.com/zh-CN/legal/terms" target="_blank" rel="noopener noreferrer">服务条款</a><a href="https://vxture.com/zh-CN/legal/privacy" target="_blank" rel="noopener noreferrer">隐私政策</a><a href="https://vxture.com/zh-CN/legal/copyright" target="_blank" rel="noopener noreferrer">版权声明</a></nav></div></footer>
 </div>;
}
