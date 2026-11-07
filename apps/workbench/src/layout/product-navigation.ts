// Product terminology is independent of stable route keys and stored record IDs.
export const moduleNames={space:'空间预览',delivery:'发布与服务',data:'数据管理',build:'构建中心',ontology:'语义本体',association:'空间关联'};
export type ModuleRoute=keyof typeof moduleNames;
// Business scope is independent of the current, transitional menu grouping.
// Shared support does not grant cross-scene access or change record ownership.
export const moduleScopes:Record<ModuleRoute,'support'|'scene'>={
 data:'support',ontology:'support',space:'scene',delivery:'scene',build:'scene',association:'scene',
};
export const moduleGroups=[
 {title:'共用支撑',items:[{route:'data',icon:'database',description:'原始、过程与成果数据目录'},{route:'ontology',icon:'cube',description:'共用类型、属性与本体规则'}]},
 {title:'场景工作',items:[{route:'build',icon:'workflow',description:'构建、核对与选择模型候选'},{route:'association',icon:'link',description:'场景语义、几何与业务关联'},{route:'delivery',icon:'package',description:'固定发布、在线服务与离线交付'},{route:'space',icon:'cube',description:'浏览场景固定发布与双视图'}]},
] as const;
