export function collectionImpact<T>(before:T[],after:T[],key:(item:T)=>string){
 const old=new Map(before.map(item=>[key(item),item])),next=new Map(after.map(item=>[key(item),item]));
 const added=after.filter(item=>!old.has(key(item))).length;
 const removed=before.filter(item=>!next.has(key(item))).length;
 const modified=after.filter(item=>old.has(key(item))&&JSON.stringify(old.get(key(item)))!==JSON.stringify(item)).length;
 return `新增 ${added} 项、修改 ${modified} 项、移除 ${removed} 项`;
}
type DeviceRelation={space_id:string;purposes:string[];usage_modes:string[]};
export function reducedDeviceRelations(before:DeviceRelation[],after:DeviceRelation[]){
 return before.filter(old=>{const next=after.find(item=>item.space_id===old.space_id);return !next||old.purposes.some(p=>!next.purposes.includes(p))||old.usage_modes.some(mode=>!next.usage_modes.includes(mode));}).length;
}
