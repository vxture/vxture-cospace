export type Bounds=[number[],number[]];
export type Lod={level:number;step:number;points:number;bytes:number;sha256:string};
export type Tile={id:string;source:number;bounds:Bounds;source_points:number;lods:Lod[]};
export type CloudDirectory={configured:true;profile:string;space_id:string;index_sha256:string;scene_manifest_sha256:string;name:string;unit_basis:string;origin:number[];sources:{name:string;sha256:string;points:number;bounds:Bounds}[];tiles:Tile[];display_point_budget:number;cache_point_budget:number;max_visible_tiles:number};
export const validBounds=(b:unknown):b is Bounds=>Array.isArray(b)&&b.length===2&&b.every(r=>Array.isArray(r)&&r.length===3&&r.every(Number.isFinite))&&b[0].every((n:number,i:number)=>n<=b[1][i]);
const sha=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export function directory(value:CloudDirectory,space:string):CloudDirectory {
 if(value.profile!=='cospace.scene-pointcloud-workspace/0.1'||value.space_id!==space||value.configured!==true||!sha(value.index_sha256)||!sha(value.scene_manifest_sha256)||value.display_point_budget!==150000||value.cache_point_budget!==300000||value.max_visible_tiles!==96||!Array.isArray(value.sources)||!value.sources.length||value.sources.length>32||!Array.isArray(value.tiles)||value.tiles.length>10000)throw Error('场景分块清单无效，请重新读取。');
 if(typeof value.name!=='string'||!Array.isArray(value.origin)||value.origin.length!==3||!value.origin.every(Number.isFinite)||typeof value.unit_basis!=='string')throw Error('场景坐标信息无效。');
 if(value.sources.some(s=>typeof s.name!=='string'||!sha(s.sha256)||!Number.isSafeInteger(s.points)||s.points<1||!validBounds(s.bounds))||new Set(value.sources.map(s=>s.name)).size!==value.sources.length)throw Error('来源清单无效。');
 if(value.tiles.some(t=>!/^t[0-9]{5}$/.test(t.id)||!Number.isInteger(t.source)||t.source<0||t.source>=value.sources.length||!validBounds(t.bounds)||!Number.isSafeInteger(t.source_points)||t.source_points<1||!Array.isArray(t.lods)||t.lods.length!==3||t.lods.some((l,i)=>l.level!==i||l.step!==[.25,1,4][i]||!Number.isInteger(l.points)||l.points<1||l.points>50000||l.bytes!==l.points*15||!sha(l.sha256)))||new Set(value.tiles.map(t=>t.id)).size!==value.tiles.length)throw Error('空间分块索引无效。');
 return value;
}
export function fullBounds(data:CloudDirectory):Bounds {
 return [Array.from({length:3},(_,i)=>Math.min(...data.sources.map(s=>s.bounds[0][i]))),Array.from({length:3},(_,i)=>Math.max(...data.sources.map(s=>s.bounds[1][i]))+1e-5)];
}
export function intersects(a:Bounds,b:Bounds){return a[0].every((v,i)=>a[1][i]>=b[0][i]&&v<b[1][i]);}
export type DisplayTile={tile:Tile;lod:Lod};
// Coarsen every intersecting source tile together; never silently drop coverage.
export function plan(tiles:Tile[],level:number,budget=150000):DisplayTile[]{
 if(tiles.length>96)throw Error('视口内分块过多，请缩小范围或减少来源。');
 for(let i=level;i<3;i++){const items=tiles.map(tile=>({tile,lod:tile.lods[i]}));if(items.reduce((n,t)=>n+t.lod.points,0)<=budget)return items;}
 throw Error('视口显示量超出预算，请缩小范围。');
}
export type TileData={positions:Float32Array;colors:Float32Array;points:number};
export async function decodeTile(raw:ArrayBuffer,lod:Lod):Promise<TileData>{
 if(raw.byteLength!==lod.bytes)throw Error('显示分块长度不匹配。');
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw))).map(v=>v.toString(16).padStart(2,'0')).join('');
 if(digest!==lod.sha256)throw Error('显示分块摘要变化，请重新读取。');
 const positions=new Float32Array(raw,0,lod.points*3),rgb=new Uint8Array(raw,lod.points*12),colors=new Float32Array(lod.points*3);
 if(!positions.every(Number.isFinite))throw Error('显示坐标无效。');
 for(let i=0;i<rgb.length;i++){const c=rgb[i]/255;colors[i]=c<=.04045?c/12.92:Math.pow((c+.055)/1.055,2.4);}
 return {positions,colors,points:lod.points};
}
export class TileCache {
 private values=new Map<string,TileData>();
 readonly budget:number;
 constructor(budget=300000){this.budget=budget;}
 get points(){return [...this.values.values()].reduce((n,v)=>n+v.points,0);}
 get size(){return this.values.size;}
 get(key:string){const value=this.values.get(key);if(value){this.values.delete(key);this.values.set(key,value);}return value;}
 put(key:string,value:TileData){if(value.points>this.budget)return;this.values.delete(key);this.values.set(key,value);while(this.points>this.budget||this.values.size>96)this.values.delete(this.values.keys().next().value!);}
 clear(){this.values.clear();}
}
