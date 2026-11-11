import test from 'node:test';
import assert from 'node:assert/strict';
import {displayPoints,createAdministrativeLayer} from '../../apps/workbench/src/layout/amap-sdk.ts';
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

import {defaultMapPreferences,normalizeMapPreferences,mapIsDark,mapFeatures,readMapPreferences} from '../../apps/workbench/src/layout/map-preferences.ts';
test('map preferences validate saved data and resolve follow mode against the current global theme',()=>{
 assert.deepEqual(normalizeMapPreferences(null),defaultMapPreferences);
 assert.equal(mapIsDark(defaultMapPreferences,'light'),true);
 assert.equal(defaultMapPreferences.administrative,true);
 assert.deepEqual(mapFeatures(defaultMapPreferences),['bg','road','building']);
 const saved=normalizeMapPreferences({appearance:'follow',roads:false,legend:false,administrative:true,scrollZoom:'false',directoryExpanded:false,unknown:'ignored'});
 assert.equal(saved.administrative,true);assert.equal(normalizeMapPreferences({administrative:'true'}).administrative,true);
 assert.equal(saved.scrollZoom,true);assert.equal(saved.directoryExpanded,false);assert.equal(saved.legend,false);
 assert.equal(mapIsDark(saved,'light'),false);assert.equal(mapIsDark(saved,'dark'),true);
 assert.equal(mapIsDark({...saved,appearance:'light'},'dark'),false);
 assert.equal(mapIsDark({...saved,appearance:'dark'},'light'),true);
 assert.deepEqual(mapFeatures(saved),['bg','building']);
 assert.equal(normalizeMapPreferences({appearance:'invalid'}).appearance,'dark');
});
test('persisted settings survive a fresh read and corrupt or blocked storage falls back safely',()=>{
 const previous=globalThis.localStorage;
 try{
  const saved={...defaultMapPreferences,appearance:'dark',roads:false,administrative:true,autoFit:false,legend:false};
  globalThis.localStorage={getItem:()=>JSON.stringify(saved)};
  assert.deepEqual(readMapPreferences(),saved);
  globalThis.localStorage={getItem:()=>'{broken'};assert.deepEqual(readMapPreferences(),defaultMapPreferences);
  globalThis.localStorage={getItem:()=>{throw Error('blocked');}};assert.deepEqual(readMapPreferences(),defaultMapPreferences);
 }finally{if(previous===undefined)delete globalThis.localStorage;else globalThis.localStorage=previous;}
});

test('administrative enhancement loads the official layer only when needed and rejects unavailable plugins',async()=>{
 let options,plugins=0;const layer={setMap(){},setStyles(){}};
 const sdk={plugin(name,done){assert.equal(name,'AMap.DistrictLayer');plugins++;sdk.DistrictLayer={Country:class{constructor(value){options=value;return layer;}}};done();}};
 assert.equal(await createAdministrativeLayer(sdk),layer);
 assert.equal(plugins,1);assert.equal(options.depth,1);assert.equal(options.styles.fill,'rgba(0,0,0,0)');
 await createAdministrativeLayer(sdk);assert.equal(plugins,1);
 await assert.rejects(createAdministrativeLayer({plugin:(_name,done)=>done()}),/行政区划图层暂不可用/);
});
