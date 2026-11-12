// Historical manifests can lack summary metadata. Keep their record pages usable
// without treating missing counts as zero or rendering a partially checked model.
export function hasPreviewModelSummary(value:unknown):boolean{
 if(!value||typeof value!=='object')return false;
 const model=value as {construction?:{model_points?:unknown};human_view?:{path?:unknown};agent_view?:{path?:unknown;surface_cells?:unknown};members?:Record<string,{bytes?:unknown}>};
 const count=(n:unknown)=>typeof n==='number'&&Number.isSafeInteger(n)&&n>=0;
 return count(model.construction?.model_points)&&count(model.agent_view?.surface_cells)
  &&[model.human_view?.path,model.agent_view?.path,'spatial.npz'].every(path=>typeof path==='string'&&!!path&&count(model.members?.[path]?.bytes));
}
