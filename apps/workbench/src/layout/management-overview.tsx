import React from 'react';
import {Link} from 'react-router-dom';
import {ArrowRight,Users,IdentificationCard,Gear,TreeStructure,Database,Cube} from '@phosphor-icons/react';
import {managementHref,productRoleDefinitions} from './management-contract';
import {useRecordNavigation,recordLink} from './record-navigation';

type Entry={title:string;description:string;detail:string;href?:string;icon:React.ElementType};
function ConfigurationCards({entries}:{readonly entries:readonly Entry[]}){
 return <div className="management-entry-grid">{entries.map(entry=>{const Icon=entry.icon;const content=<><Icon size={24} className="management-entry-icon"/><h2>{entry.title}</h2><p>{entry.description}</p><div className="management-entry-detail"><span>{entry.detail}</span>{entry.href&&<ArrowRight size={18}/>}</div></>;return entry.href?<Link key={entry.title} to={entry.href} className="management-entry">{content}</Link>:<div key={entry.title} className="management-entry" aria-disabled="true">{content}</div>;})}</div>;
}
export function ManagementOverview(){
 const {space}=useRecordNavigation();
 return <><ConfigurationCards entries={[
  {title:'角色说明',description:'了解所有者、管理者、工程师和查看者各自能做什么。',detail:'四种固定角色 · 按范围生效',href:managementHref('settings',space,'roles'),icon:IdentificationCard},
  {title:'权限管理',description:'为需要编辑、构建或发布的成员分配场景角色，查看调整记录。',detail:'普通成员默认可查看工作区场景',href:managementHref('settings',space,'permissions'),icon:Users},
  {title:'高级配置',description:'进入语义规则、资料来源和场景基本信息等现有配置。',detail:'各项操作按实际权限校验',href:managementHref('settings',space,'advanced'),icon:Gear},
 ]}/><section className="management-card"><h2>配置范围</h2><p>此处管理 CoSpace 的产品权限与业务配置。组织成员、工作区身份和订阅由平台统一维护。</p><p className="text-body-small text-muted-foreground">权限管理用于补充场景操作权限；查看本工作区场景无需逐人申请。角色与场景范围共同决定最终可执行的操作。</p></section></>;
}
export function RoleDefinitions(){
 return <><div className="management-role-list">{productRoleDefinitions.map(item=><section className="management-card" key={item.role}><h2>{item.role}</h2><p className="text-body-small text-muted-foreground">{item.scope}</p><dl className="management-role-facts"><div><dt>场景操作</dt><dd>{item.scene}</dd></div><div><dt>高级配置</dt><dd>{item.advanced}</dd></div><div><dt>人员授权</dt><dd>{item.members}</dd></div></dl></section>)}</div><p className="text-body-small text-muted-foreground">当前使用固定角色，不支持自定义角色或编辑权限组合。管理者只能在自身管理范围内分配角色；工程师不能管理人员授权。</p></>;
}
export function AdvancedConfiguration(){
 const {space}=useRecordNavigation();
 return <><ConfigurationCards entries={[
  {title:'语义规则',description:'维护共用类型、属性、关系及本体版本。',detail:'系统高级配置 · 管理者维护',href:'/ontology',icon:TreeStructure},
  {title:'资料来源',description:'配置当前场景可登记的资料来源，保留变更记录。',detail:space?'当前所选场景 · 工程师及以上维护':'请先从“我的场景”选择场景',href:space?recordLink('data',{space,tab:'sources'}):undefined,icon:Database},
  {title:'场景基本信息',description:'维护场景名称、用途与位置，查看修改历史。',detail:space?'当前所选场景 · 按场景权限维护':'请先从“我的场景”选择场景',href:space?recordLink('build',{space,tab:'info'}):undefined,icon:Cube},
 ]}/>{!space&&<Link to="/space" className="text-primary underline">前往我的场景</Link>}<p className="text-body-small text-muted-foreground">业务规则在各自页面维护，操作按当前授权范围生效。</p></>;
}
