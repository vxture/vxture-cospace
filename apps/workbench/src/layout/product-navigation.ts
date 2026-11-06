// Product terminology is independent of stable route keys and stored record IDs.
export const moduleNames={space:'空间预览',delivery:'态势服务',data:'数据管理',build:'构建中心',ontology:'语义本体',association:'空间关联'};
export const moduleGroups=[
 {title:'使用',items:[{route:'space',icon:'cube',description:'按场景浏览固定发布与双视图'},{route:'delivery',icon:'package',description:'场景版本发布、在线服务与离线交付'}]},
 {title:'构建',items:[{route:'data',icon:'database',description:'场景空间的资料、历史版本与来源'},{route:'build',icon:'workflow',description:'当前场景的构建任务、候选与校核'}]},
 {title:'定义',items:[{route:'ontology',icon:'cube',description:'共用类型、属性、关系与本体版本'},{route:'association',icon:'link',description:'当前场景的语义、几何与业务关联'}]},
] as const;
