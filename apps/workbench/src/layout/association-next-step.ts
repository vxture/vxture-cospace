export function associationNextStep(view:string,selected:boolean){
 const next:Record<string,{tab:string;label:string;description:string}>={
  overview:{tab:'objects',label:'开始对象管理',description:'先建立对象并核对类型、属性与模型位置。'},
  objects:{tab:'relations',label:'继续空间关系',description:'对象核对后，继续维护空间归属与连接关系。'},
  relations:{tab:'business',label:'继续业务关联',description:'空间关系核对后，按业务需要补充台账关联。'},
 };
 if(next[view])return {module:'association' as const,...next[view]};
 return selected?{module:'delivery' as const,tab:'overview',label:'前往服务发布',description:'核对已保存的关联内容后，进入固定版本发布准备。'}:{module:'build' as const,tab:'candidate',label:'前往成果核对',description:'关联修改产生的新候选需要先核对选择，再继续后续环节。'};
}
