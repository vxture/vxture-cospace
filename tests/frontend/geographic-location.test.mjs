import test from 'node:test';
import assert from 'node:assert/strict';
import {altitudeLabel,locationFromDraft,locationLabel} from '../../apps/workbench/src/layout/geographic-location.ts';
import {globePosition} from '../../apps/workbench/src/layout/globe-coordinates.ts';
const draft={longitude:'120',latitude:'30',altitude:'50',crs:'WGS84',reference:'ellipsoid',source:'Survey A'};
test('only declared ellipsoid heights become absolute globe positions',()=>{
 const value=locationFromDraft(draft);
 assert.deepEqual(globePosition(value),[120,30,50]);
 for(const reference of ['unknown','orthometric',undefined]){
  assert.deepEqual(globePosition({...value,altitude_reference:reference}),[120,30]);
 }
 assert.equal(globePosition({...value,crs:'GCJ02'}),null);
 assert.equal(globePosition({...value,altitude:Infinity}),null);
 assert.equal(altitudeLabel({...value,altitude_reference:undefined}),'50 m · 基准未明确');
 assert.equal(locationLabel({...value,crs:'GCJ02'}),'已登记 · 三维坐标待转换');
});
test('save and unsaved-navigation share full coordinate validation',()=>{
 assert.equal(locationFromDraft({...draft,longitude:'',latitude:'',altitude:''}),null);
 for(const patch of [{longitude:''},{latitude:''},{longitude:'181'},{latitude:'NaN'},{altitude:'100001'},{altitude:'Infinity'}])assert.throws(()=>locationFromDraft({...draft,...patch}));
 assert.deepEqual(locationFromDraft({...draft,altitude:'0'}),{longitude:120,latitude:30,altitude:0,altitude_reference:'ellipsoid',crs:'WGS84',source:'Survey A'});
});
