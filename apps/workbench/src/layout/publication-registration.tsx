import React,{useState} from 'react';
import {Button} from '@vxture/design-system';
import {MapPin} from '@phosphor-icons/react';
import {RegistrationMap} from './registration-map';
import {businessEndpoint} from './business-endpoint';

export function PublicationRegistration({publicationId}:{publicationId:string}){
 const [open,setOpen]=useState(false);
 return <section className="publication-semantic-section" aria-label="固定配准成果"><h4>核准配准成果</h4><p>读取本次发布固定的基准、转换和对象点锚，后续工作修订不改变此成果。</p><Button size="sm" variant="outline" onClick={()=>setOpen(true)}><MapPin size={16}/>查看固定对象地图</Button><RegistrationMap open={open} onClose={()=>setOpen(false)} url={businessEndpoint+`/publications/${encodeURIComponent(publicationId)}/api/registration`}/></section>;
}
