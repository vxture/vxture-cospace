import React from 'react';
import {moduleNames,moduleGroups} from './product-navigation';
import {recordLink} from './record-navigation';
const progress={
 space:{done:'真实双视图、版本切换、授权空间目录及基本信息保存与历史',next:'待完善：真实平台客户端联调与空间创建'},
 delivery:{done:'固定发布、分发控制、离线消费与查询/导出/发布分权',next:'待完善：真实平台联调与交付验收'},
 data:{done:'采集批次、成果追溯、状态历史及逐空间来源配置与登记权限',next:'待完善：更多输入适配与现场采集接入'},
 build:{done:'样本构建、候选差异与人工核对选择',next:'待完善：算法选配与几何增量更新'},
 ontology:{done:'固定本体版本、类型及关系规则与草稿校验',next:'待完善：本体编辑与行业规则映射'},
 association:{done:'对象锚点、固定台账与对象关系候选',next:'待完善：画面点选、现场核实与外部同步'},
};
export function ModuleProgress(){return <details className="rounded-lg border border-border p-lg"><summary className="cursor-pointer text-body-small font-medium">项目进度 · 三类六入口</summary><p className="mt-md text-label-small text-muted-foreground">截至2026-11-03的实施记录，非实时运行状态或产品验收。两类样本已完成六入口流程、成果生命周期及在线/离线消费验证；各空间当前阶段请点击“查看流程”。平台身份已接入空间目录、资产、查询、下载及写操作的服务端权限检查；查看、工程和管理角色在独立样本副本验证通过，含撤权和服务重启。8769为带权限的本地模拟平台入口，8767保留为内部工程预览。下一步：配置CoSpace平台客户端，完成真实平台联调；成员授权和空间创建暂由受控管理流程处理。</p><div className="mt-lg grid grid-cols-1 gap-xl md:grid-cols-3">{moduleGroups.map(group=><section key={group.title}><h2 className="mb-md text-body-small font-medium">{group.title}</h2><div className="flex flex-col gap-lg">{group.items.map(item=><div key={item.route}><a className="text-body-small font-medium text-primary" href={item.route==='space'?'/space':recordLink(item.route,{})}>{moduleNames[item.route]}</a><p className="mt-xs text-label-small text-muted-foreground">已接通：{progress[item.route].done}</p><p className="mt-xs text-label-small text-muted-foreground">{progress[item.route].next}</p></div>)}</div></section>)}</div></details>;}
