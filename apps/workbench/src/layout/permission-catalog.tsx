import React,{useState} from 'react';
import {Button,Drawer,Input,NativeSelect,Table,TableHeader,TableHead,TableRow,TableBody,TableCell} from '@vxture/design-system';

type Permission={name:string;group:string;roles:readonly string[];description:string};
const operators=['所有者','管理者','工程师'];
const administrators=['所有者','管理者'];
const permissions:Permission[]=[
 {name:'进入我的场景',group:'功能入口',roles:[...operators,'查看者'],description:'进入场景列表，列表只返回当前数据范围内的场景。'},
 {name:'打开空间全景地图',group:'功能入口',roles:[...operators,'查看者'],description:'通过地图查看数据范围内的场景，地图不会扩大数据范围。'},
 {name:'查看与预览场景',group:'场景浏览',roles:[...operators,'查看者'],description:'平台已授权的成员默认可查看当前数据范围内的场景。'},
 {name:'查询场景内容',group:'场景浏览',roles:[...operators,'查看者'],description:'在当前工作区场景内查询已提供的内容。'},
 {name:'查看服务对象',group:'场景浏览',roles:[...operators,'查看者'],description:'读取场景关联的服务对象信息。'},
 {name:'新建场景',group:'场景操作',roles:operators,description:'所有者或已拥有工程师、管理者场景授权的成员可以新建场景。'},
 {name:'维护名称与描述',group:'场景操作',roles:operators,description:'在已授权场景内维护名称、用途和描述。'},
 {name:'编辑场景位置',group:'场景操作',roles:operators,description:'在已授权场景内调整空间位置。'},
 {name:'管理资料',group:'场景操作',roles:operators,description:'在已授权场景内登记、维护资料与资料来源。'},
 {name:'运行模型构建',group:'场景操作',roles:operators,description:'在已授权场景内发起构建和查看处理结果。'},
 {name:'编辑空间关联',group:'场景操作',roles:operators,description:'在已授权场景内维护空间对象关联。'},
 {name:'管理服务发布',group:'场景操作',roles:operators,description:'在已授权场景内管理服务发布。'},
 {name:'导出场景成果',group:'场景操作',roles:operators,description:'导出已授权场景内允许导出的成果。'},
 {name:'管理服务对象',group:'场景操作',roles:operators,description:'在已授权场景内维护服务对象及其关联。'},
 {name:'系统高级配置',group:'配置管理',roles:administrators,description:'维护系统高级配置，操作仍需满足对应服务的权限校验。'},
 {name:'设置成员数据范围',group:'成员权限',roles:['所有者'],description:'独立限制成员可访问的场景，不增加功能权限。当前仅工作区所有者可调整整个工作区的数据范围。'},
 {name:'分配成员场景角色',group:'成员权限',roles:administrators,description:'所有者可管理本工作区全部已绑定场景；管理者只能调整自己管理范围内的场景授权。'},
];
export function PermissionCatalog(){
 const [query,setQuery]=useState(''),[group,setGroup]=useState(''),[selected,setSelected]=useState<Permission|null>(null);
 const filtered=permissions.filter(item=>item.name.includes(query)&&(!group||item.group===group));
 return <><div className="management-card-heading"><h2>权限清单</h2><span className="text-body-small text-muted-foreground">{permissions.length} 项操作 · 4 种固定角色</span></div><div className="management-member-toolbar"><label>搜索权限<Input aria-label="搜索权限" value={query} placeholder="按操作名称搜索" onChange={e=>setQuery(e.target.value)}/></label><label>业务模块<NativeSelect aria-label="筛选权限模块" value={group} onChange={e=>setGroup(e.target.value)}><option value="">全部模块</option>{[...new Set(permissions.map(item=>item.group))].map(value=><option key={value}>{value}</option>)}</NativeSelect></label></div><div className="management-member-table"><Table><TableHeader><TableRow><TableHead>操作权限</TableHead><TableHead>业务模块</TableHead><TableHead>授权角色</TableHead><TableHead data-table-actions>操作</TableHead></TableRow></TableHeader><TableBody>{filtered.map(item=><TableRow key={item.name}><TableCell>{item.name}</TableCell><TableCell>{item.group}</TableCell><TableCell><div className="management-role-badges">{item.roles.map(role=><span key={role}>{role}</span>)}</div></TableCell><TableCell data-table-actions><Button variant="ghost" size="sm" onClick={()=>setSelected(item)}>查看详情</Button></TableCell></TableRow>)}</TableBody></Table></div>{!filtered.length&&<p>没有匹配的权限。</p>}<p className="text-body-small text-muted-foreground">共 {filtered.length} 项 · 权限按角色及实际授权范围生效</p><Drawer open={!!selected} onClose={()=>setSelected(null)} side="right" width="md" title="权限详情" description={selected?.name} closeLabel="关闭权限详情">{selected&&<div className="management-drawer-content"><dl className="management-information"><div><dt>业务模块</dt><dd>{selected.group}</dd></div><div><dt>授权角色</dt><dd>{selected.roles.join('、')}</dd></div></dl><p>{selected.description}</p><p className="text-body-small text-muted-foreground">角色权限组合由产品定义。人员的实际授权在成员管理、场景管理中维护，保存时由服务端校验。</p></div>}</Drawer></>;
}
