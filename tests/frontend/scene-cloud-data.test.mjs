import {test} from 'node:test';
import assert from 'node:assert/strict';
import {plan,TileCache,decodeTile,validBounds,intersects,directory,fullBounds} from '../../apps/workbench/src/layout/scene-cloud-data.ts';
const tile=(id,counts=[100,20,5])=>({id,source:0,bounds:[[0,0,0],[1,1,1]],source_points:100,lods:counts.map((points,level)=>({level,points,step:[.25,1,4][level]}))});
test('display planning coarsens all intersecting tiles without silently dropping coverage',()=>{
 const items=plan([tile('one'),tile('two')],0,50);assert.equal(items.length,2);assert.ok(items.every(i=>i.lod.level===1));
 assert.throws(()=>plan([tile('one')],0,1));assert.throws(()=>plan(Array.from({length:97},(_,i)=>tile(String(i))),2));
 assert.deepEqual(plan([],0),[]);
});
test('cache has point and entry limits, updates LRU hits, isolates replacement',()=>{
 const cache=new TileCache(10),point=points=>({positions:new Float32Array(points*3),colors:new Float32Array(points*3),points});
 cache.put('a',point(4));cache.put('b',point(4));assert.ok(cache.get('a'));cache.put('c',point(4));assert.equal(cache.get('b'),undefined);assert.equal(cache.points,8);
 cache.put('a',point(2));assert.equal(cache.points,6);cache.put('oversize',point(11));assert.equal(cache.points,6);cache.clear();assert.equal(cache.points,0);
 const many=new TileCache(1000);for(let i=0;i<100;i++)many.put(String(i),point(1));assert.equal(many.size,96);
});
test('binary decode requires exact digest and bounded layout',async()=>{
 const raw=new ArrayBuffer(15);new Float32Array(raw,0,3).set([1,2,3]);new Uint8Array(raw,12).set([255,128,0]);
 const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw))).map(v=>v.toString(16).padStart(2,'0')).join('');
 const lod={level:0,points:1,bytes:15,step:.25,sha256:sha};const value=await decodeTile(raw,lod);
 assert.deepEqual([...value.positions],[1,2,3]);assert.equal(value.colors[0],1);assert.equal(value.colors[2],0);
 await assert.rejects(decodeTile(raw,{...lod,sha256:'0'.repeat(64)}));await assert.rejects(decodeTile(raw,{...lod,bytes:14}));
});
test('ROI is half open and malformed/nonfinite bounds are rejected',()=>{
 assert.ok(validBounds([[0,0,0],[1,1,1]]));assert.equal(validBounds([[0,0,0],[Infinity,1,1]]),false);
 assert.equal(validBounds([[1,0,0],[0,1,1]]),false);assert.equal(intersects([[1,0,0],[2,1,1]],[[0,0,0],[1,1,1]]),false);
});


test('directory validates source binding, coordinate metadata and tile budgets',()=>{
 const sha='a'.repeat(64),space='space-'+'1'.repeat(16);
 const value={configured:true,profile:'cospace.scene-pointcloud-workspace/0.1',space_id:space,index_sha256:sha,scene_manifest_sha256:sha,
  display_point_budget:150000,cache_point_budget:300000,max_visible_tiles:96,name:'scene',origin:[1,2,3],unit_basis:'assumed_metre_for_flow_validation',
  sources:[{name:'one.laz',sha256:sha,points:100,bounds:[[0,0,0],[1,1,1]]}],tiles:[{...tile('t00000'),lods:tile('t00000').lods.map(l=>({...l,bytes:l.points*15,sha256:sha}))}]};
 assert.equal(directory(value,space),value);assert.equal(fullBounds(value)[1][0],1.00001);
 for(const change of [{space_id:'other'},{origin:[NaN,2,3]},{display_point_budget:1},{sources:[...value.sources,...value.sources]},
  {tiles:[{...value.tiles[0],source:1}]},{tiles:[{...value.tiles[0],source_points:-1}]},{tiles:[{...value.tiles[0],lods:[]}]}])assert.throws(()=>directory({...value,...change},space));
});
