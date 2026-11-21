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
import {registrationNextStep} from '../../apps/workbench/src/layout/registration-next-step.ts';
import {associationNextStep} from '../../apps/workbench/src/layout/association-next-step.ts';
import {publicationForTarget} from '../../apps/workbench/src/layout/publication-target.ts';

test('publication handoffs never substitute a historical release for an unpublished model',()=>{
 const releases=[{id:'latest',candidate_id:'other-model'},{id:'matched',candidate_id:'target-model'}];
 assert.equal(publicationForTarget(releases,{job:'target-model'}).id,'matched');
 assert.equal(publicationForTarget(releases,{job:'new-model'}),undefined);
 assert.equal(publicationForTarget(releases,{publication:'missing',job:'target-model'}),undefined);
 assert.equal(publicationForTarget(releases,{publication:'latest',job:'target-model'}).id,'latest');
 assert.equal(publicationForTarget(releases,{}).id,'latest');
});

test('registration handoff requires saved checks, independent review and valid adopted approval',()=>{
 const now=Date.parse('2026-11-22T00:00:00Z');
 const facts={dirty:false,hasDocument:true,checksPassed:true,synthetic:false,reviewStatus:'draft',canEdit:true,canReview:true,actor:'manager',authoredBy:'author',approvedRevision:null,adoptedRevision:null,validFrom:'2026-11-21T00:00:00Z',validUntil:'2026-11-23T00:00:00Z'};
 assert.equal(registrationNextStep({...facts,dirty:true},now).action,'save');
 assert.equal(registrationNextStep({...facts,hasDocument:false},now).action,'import');
 assert.equal(registrationNextStep(facts,now).action,'submit');
 for(const changes of [{checksPassed:false},{synthetic:true},{canEdit:false}])assert.equal(registrationNextStep({...facts,...changes},now).action,null);
 assert.equal(registrationNextStep({...facts,reviewStatus:'submitted'},now).action,'approve');
 for(const changes of [{actor:'author'},{actor:''},{canReview:false}])assert.equal(registrationNextStep({...facts,reviewStatus:'submitted',...changes},now).action,null);
 const approved={...facts,reviewStatus:'approved',approvedRevision:3};
 assert.equal(registrationNextStep(approved,now).action,'adopt');
 assert.equal(registrationNextStep({...approved,adoptedRevision:3},now).action,'association');
 for(const validUntil of ['2026-11-21T00:00:00Z','invalid'])assert.equal(registrationNextStep({...approved,adoptedRevision:3,validUntil},now).action,null);
 assert.equal(registrationNextStep({...approved,adoptedRevision:3,validFrom:'2026-11-23T00:00:00Z'},now).action,null);
});

test('association follows objects, relations and business before publication and reviews unselected candidates',()=>{
 for(const [view,tab] of [['overview','objects'],['objects','relations'],['relations','business']]){
  for(const selected of [true,false])assert.deepEqual([associationNextStep(view,selected).module,associationNextStep(view,selected).tab],['association',tab]);
 }
 assert.equal(associationNextStep('business',true).module,'delivery');
 assert.deepEqual([associationNextStep('business',false).module,associationNextStep('business',false).tab],['build','candidate']);
});
