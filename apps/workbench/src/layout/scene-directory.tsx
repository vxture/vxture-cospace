import React from 'react';
import {Input} from '@vxture/design-system';
import {Database,Cube,MagnifyingGlass,CaretRight} from '@phosphor-icons/react';

export type ScenePublication={id:string;created_at:string;preview_url:string;candidate_id:string;lifecycle_state?:string};
export type SceneSpace={id:string;name:string;project_id:string;project_name?:string;description?:string;address?:string;overview_url?:string;state?:string;publication_id?:string|null;capabilities?:string[];publications?:ScenePublication[]};
export function SceneDirectory({spaces,current,workspace,search,onSearch,onChoose,loading,error,library=false}:{spaces:SceneSpace[];current:string;workspace:string;search:string;onSearch:(s:string)=>void;onChoose:(id:string)=>void;loading:boolean;error:string;library?:boolean}){
 const visible=spaces.filter(s=>s.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
 return <aside id="data-scene-sidebar" className="data-sidebar" aria-label="场景空间目录">
  <div className="data-workspace-id"><span className="data-workspace-symbol"><Database size={19} weight="duotone"/></span><div><span className="data-eyebrow">WORKSPACE</span><strong title={workspace}>{workspace}</strong></div></div>
  <div className="data-sidebar-label"><span>场景空间</span><span>{spaces.length}</span></div>
  <div className="data-search data-scene-search"><MagnifyingGlass size={15}/><Input aria-label="搜索场景空间" placeholder="搜索场景空间" value={search} onChange={e=>onSearch(e.target.value)}/></div>
  <nav className="data-scenes" aria-label="选择场景空间">
   {loading&&<p className="data-subtle" role="status">正在读取场景…</p>}
   {error&&<p className="data-subtle" role="alert">{error}</p>}
   {visible.map(s=><button key={s.id} className={`data-scene ${s.id===current?'is-active':''}`} aria-current={s.id===current?'true':undefined} onClick={()=>onChoose(s.id)}><span className="data-scene-symbol"><Cube size={19} weight="duotone"/></span><span><strong>{s.name}</strong><small>{s.publications?.length?`${s.publications.length} 个固定发布`:'暂无固定发布'}</small></span><CaretRight size={12}/></button>)}
   {!loading&&!error&&!visible.length&&<p className="data-subtle">{spaces.length?'没有匹配的场景':'暂无可访问的场景空间'}</p>}
  </nav>
  <div className="data-sidebar-bottom"><span className="data-eyebrow">{library?'共用规则 · 场景应用':'场景数据链路'}</span><div className="data-mini-flow"><span>资料</span><CaretRight size={12}/><span>模型</span><CaretRight size={12}/><span>服务</span></div><p>{library?'本体版本共用，关联实例按场景独立':'一个场景空间，管理一个三维场景'}</p></div>
 </aside>;
}
