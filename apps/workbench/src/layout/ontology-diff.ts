export type Difference={path:string;kind:'added'|'removed'|'changed';before:string;after:string;review:boolean};
const pointer=(value:string)=>value.replaceAll('~','~0').replaceAll('/','~1');
function flatten(value:unknown,path='',result:Record<string,string>={}){
 if(!path&&value&&typeof value==='object'&&!Object.keys(value).length)return result;
 if(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length){
  for(const name of Object.keys(value).sort())flatten((value as Record<string,unknown>)[name],path+'/'+pointer(name),result);
 }else result[path]=JSON.stringify(value);
 return result;
}
export function compareDefinitions(before:Record<string,unknown>,after:Record<string,unknown>){
 if(before.ontology_id!==after.ontology_id)throw Error('只能比较同一本体的固定版本。');
 const omit=(value:Record<string,unknown>)=>Object.fromEntries(Object.entries(value).filter(([name])=>!['version','ontology_id'].includes(name)));
 const left=flatten(omit(before)),right=flatten(omit(after));
 const changes:Difference[]=[];
 for(const path of [...new Set([...Object.keys(left),...Object.keys(right)])].sort()){
  if(left[path]===right[path])continue;
  const kind=!(path in left)?'added':!(path in right)?'removed':'changed';
  changes.push({path,kind,before:left[path]??'未定义',after:right[path]??'未定义',review:!['title','description'].some(name=>path.endsWith('/'+name))});
 }
 return {total:changes.length,items:changes.slice(0,200),truncated:changes.length>200};
}
