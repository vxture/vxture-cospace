import test from 'node:test';
import assert from 'node:assert/strict';
import {globePosition} from '../../apps/workbench/src/layout/globe-coordinates.ts';
test('globe positions require valid WGS84 and never place GCJ02 or invalid coordinates on earth',()=>{
 assert.deepEqual(globePosition({longitude:105,latitude:25,crs:'WGS84'}),[105,25]);
 assert.deepEqual(globePosition({longitude:-180,latitude:90,crs:'WGS84'}),[-180,90]);
 for(const location of [undefined,{longitude:105,latitude:25,crs:'GCJ02'},{longitude:NaN,latitude:25,crs:'WGS84'},{longitude:105,latitude:Infinity,crs:'WGS84'},{longitude:181,latitude:25,crs:'WGS84'},{longitude:105,latitude:-91,crs:'WGS84'}])assert.equal(globePosition(location),null);
});
