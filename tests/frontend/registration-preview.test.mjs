import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {registrationPreview,transformRegistrationPoint,displayMetres,displayCentimetres} from '../../apps/workbench/src/layout/registration-preview-data.ts';

const fixture=JSON.parse(readFileSync(new URL('../../contracts/examples/spatial-registration-campus.json',import.meta.url),'utf8'));
const golden=JSON.parse(readFileSync(new URL('../../contracts/examples/spatial-registration-campus-report.json',import.meta.url),'utf8'));
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-10,`${a} differs from ${b}`);

test('visual horizontal and vertical errors match the independent Python report',()=>{
 const preview=registrationPreview(fixture);
 assert.equal(preview.passed,true);
 for(const key of ['horizontal_rmse_m','vertical_rmse_m','max_horizontal_m','max_vertical_m'])close(preview[key],golden.metrics.check[key]);
 preview.controls.forEach((point,i)=>{
  assert.equal(point.id,golden.controls[i].id);
  close(point.horizontal_m,golden.controls[i].horizontal_m);
  close(point.vertical_m,golden.controls[i].vertical_m);
  point.delta_m.forEach((n,j)=>close(n,golden.controls[i].delta_m[j]));
 });
});

test('transform direction and height use column vectors with a fixed unit scale',()=>{
 assert.deepEqual(transformRegistrationPoint([4,5,6],[[0,-1,0,10],[1,0,0,20],[0,0,1,-3],[0,0,0,1]]),[5,24,3]);
 assert.equal(displayMetres(.0396),'0.040');
});

test('horizontal or vertical overflow remains visible without changing the control group',()=>{
 for(const axis of [0,2]){
  const input=structuredClone(fixture);input.controls[5].target_m[axis]+=.32;
  const preview=registrationPreview(input);
  assert.equal(preview.passed,false);
  assert.equal(preview.controls[5].within_limits,false);
  assert.deepEqual(preview.controls.slice(0,3),registrationPreview(fixture).controls.slice(0,3));
 }
});

test('centimetre display rounding never changes the metre-based acceptance threshold',()=>{
 for(const axis of [0,2]){
  for(const residual of [.09999,.10001]){
   const input=structuredClone(fixture),point=input.controls[5];
   point.target_m=transformRegistrationPoint(point.source_m,input.matrix);
   point.target_m[axis]-=residual;
   const preview=registrationPreview(input),result=preview.controls[5];
   const computed=axis===0?result.horizontal_m:result.vertical_m;
   close(computed,residual);
   assert.equal(displayCentimetres(computed),'10.0');
   assert.equal(result.within_limits,residual<.1);
   assert.equal(preview.passed,residual<.1);
  }
 }
});
