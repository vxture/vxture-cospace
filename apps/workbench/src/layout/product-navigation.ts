// Product terminology is independent of stable route keys and stored record IDs.
export const moduleNames={space:'我的场景',delivery:'服务发布',data:'数据管理',build:'构建中心',ontology:'语义本体',association:'空间关联'};
export type ModuleRoute=keyof typeof moduleNames;
// Business scope is independent of the current, transitional menu grouping.
// Shared support does not grant cross-scene access or change record ownership.
export const moduleScopes:Record<ModuleRoute,'support'|'scene'>={
 data:'support',ontology:'support',space:'scene',delivery:'scene',build:'scene',association:'scene',
};
export const moduleGroups=[
 {title:'公共资源',items:[{route:'data',icon:'database',description:'原始资料与成果目录'},{route:'ontology',icon:'cube',description:'共用类型与本体规则'}]},
 {title:'场景作业',items:[{route:'build',icon:'workflow',description:'模型构建与候选核对'},{route:'association',icon:'link',description:'语义、几何与业务关联'},{route:'delivery',icon:'package',description:'版本发布与交付'},{route:'space',icon:'cube',description:'浏览空间与固定发布'}]},
] as const;
