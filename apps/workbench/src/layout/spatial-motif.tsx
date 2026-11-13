import type React from 'react';

// A decorative spatial diagram. It represents the product, not a user's scene.
export function SpatialMotif({className,children}:{readonly className?:string;readonly children?:React.ReactNode}){
 return <svg className={className} viewBox="0 0 460 255" fill="none" aria-hidden="true">
  <g stroke="currentColor" opacity=".16">
   {Array.from({length:13},(_,i)=><path key={i} d={`M${30+i*17} ${155-i*8}l204 96 M${30+i*17} ${155+i*8}l204 -96`}/>)}
  </g>
  <g stroke="currentColor" strokeLinejoin="round">
   <path fill="color-mix(in srgb,var(--primary) 8%,var(--card))" strokeOpacity=".55" d="M81 159 232 88l153 71-153 73Z"/>
   <path fill="color-mix(in srgb,var(--primary) 8%,var(--card))" strokeOpacity=".55" d="M106 123 232 64l126 59-126 60Z"/>
   <path fill="color-mix(in srgb,var(--primary) 8%,var(--card))" strokeOpacity=".55" d="M132 87 232 40l100 47-100 48Z"/>
   <path opacity=".48" d="M132 87v48l100 48 100-48V87M232 135v48M182 64v47l100 48M282 64v47l-100 48" strokeDasharray="4 4"/>
   <path opacity=".72" d="M155 157l41-19 36 17 54-25 42 20" strokeWidth="1.5"/>
   {[[155,157],[232,155],[286,130],[328,150],[232,40]].map(([x,y])=><circle key={x+':'+y} cx={x} cy={y} r="4" fill="var(--card)" strokeWidth="2"/>)}
  </g>
  {children}
 </svg>;
}
