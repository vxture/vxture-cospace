import test from 'node:test';
import assert from 'node:assert/strict';
import {displayPoints} from '../../apps/workbench/src/layout/amap-sdk.ts';
test('official JS conversion protocol batches at 40, preserves original and skips GCJ02',async()=>{
 const original=globalThis.fetch,calls=[];
 const input=Array.from({length:41},()=>({longitude:116,latitude:39,crs:'WGS84'}));input.push({longitude:120,latitude:30,crs:'GCJ02'});
 globalThis.fetch=async url=>{calls.push(String(url));const params=new URL(url,'http://localhost').searchParams;assert.equal(params.get('s'),'rsv3');assert.equal(params.get('coordsys'),'gps');assert.equal(params.has('jscode'),false);return Response.json({status:'1',locations:params.get('locations').split(';').map(()=> '116.006,39.001').join(';')});};
 try{const result=await displayPoints({},input);assert.equal(calls.length,2);assert.deepEqual(result[0],[116.006,39.001]);assert.deepEqual(result[41],[120,30]);assert.equal(input[0].longitude,116);}finally{globalThis.fetch=original;}
});
test('invalid coordinates and upstream rejection never produce misplaced pins',async()=>{
 await assert.rejects(displayPoints({},[{longitude:181,latitude:39,crs:'WGS84'}]));
 const original=globalThis.fetch;globalThis.fetch=async()=>Response.json({status:'0',info:'REJECTED'});
 try{await assert.rejects(displayPoints({},[{longitude:116,latitude:39,crs:'WGS84'}]));}finally{globalThis.fetch=original;}
});
