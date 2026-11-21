import test from 'node:test';
import assert from 'node:assert/strict';
import {validateDeclaration} from '../../apps/workbench/src/layout/pointcloud-package.ts';
import {validateCoordinateSuggestion,suggestionReason} from '../../apps/workbench/src/layout/coordinate-assistance-contract.ts';

test('intake preserves explicit multilingual directions and legacy opaque axis names',()=>{
 for(const axes of [['右','前','上'],['Right','FORWARD','Up'],['X(right)','Y_forward','Z-up'],['sensor_x','sensor_y','sensor_z']]){
  const declaration={frame_id:'source/local',axes,scope:'scene_local',description:'Imported source declaration'};
  const before=structuredClone(declaration);
  assert.doesNotThrow(()=>validateDeclaration(declaration));
  assert.deepEqual(declaration,before);
 }
 for(const axes of [['right','right','up'],['a\nb','front','up'],['../right','front','up'],['a'.repeat(41),'front','up']]){
  assert.throws(()=>validateDeclaration({frame_id:'local',axes,scope:'scene_local',description:'source'}));
 }
});

const context={space:'space-'+'a'.repeat(16),input:null,revision:null,task:'cospace-coordinate-'+'a'.repeat(32),sha256:'b'.repeat(64),evidence:'X右，Y前，Z上，单位米'};
function suggestion(){return {profile:'cospace.coordinate-assistance/0.1',space_id:context.space,input_id:null,expected_revision:null,task_id:context.task,evidence_sha256:context.sha256,proposal:{axes:[{direction:'right',evidence_quote:'X右'},{direction:'forward',evidence_quote:'Y前'},{direction:'up',evidence_quote:'Z上'}],unit:'m',unit_evidence_quote:'单位米',unresolved:[]},can_apply_axes:true,requires_confirmation:true,coordinate_transform_applied:false};}

test('model suggestions bind source text and context, preserve quotations and never imply a transform',()=>{
 const value=suggestion();assert.equal(validateCoordinateSuggestion(value,context),value);
 assert.match(suggestionReason(value),/X右/);assert.match(suggestionReason(value),/cospace-coordinate-/);
 assert.ok(suggestionReason(value).length<=500);
 for(const change of [{space_id:'foreign'},{input_id:'input-'+'c'.repeat(16)},{expected_revision:2},{task_id:'old-task'},{evidence_sha256:'wrong'},{requires_confirmation:false},{coordinate_transform_applied:true}])assert.throws(()=>validateCoordinateSuggestion({...value,...change},context));
});

test('ungrounded, unresolved and incompatible suggestions cannot be applied',()=>{
 const value=suggestion();
 const ungrounded=structuredClone(value);ungrounded.proposal.axes[0].evidence_quote='invented';assert.throws(()=>validateCoordinateSuggestion(ungrounded,context));
 const incomplete=structuredClone(value);incomplete.proposal.axes[1]={direction:null,evidence_quote:''};assert.throws(()=>validateCoordinateSuggestion(incomplete,context));
 incomplete.can_apply_axes=false;assert.equal(validateCoordinateSuggestion(incomplete,context),incomplete);
 const conflict=structuredClone(value);conflict.proposal.unresolved=['请核对冲突'];assert.throws(()=>validateCoordinateSuggestion(conflict,context));
 const millimetres=structuredClone(value);millimetres.proposal.unit='mm';millimetres.proposal.unit_evidence_quote='毫米';assert.throws(()=>validateCoordinateSuggestion(millimetres,{...context,evidence:context.evidence+'，毫米'}));
});
