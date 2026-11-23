import test from 'node:test';
import assert from 'node:assert/strict';
import {validateExact} from '../../apps/workbench/src/layout/model-exact-contract.ts';
const source={space:'space-one',candidate:'build-one',manifest:'a'.repeat(64),source:'b'.repeat(64),frame:'survey/local'};
const value=()=>({profile:'cospace.model-exact/0.1',space_id:source.space,model_id:source.candidate,source_manifest_sha256:source.manifest,source_model_sha256:source.source,frame_id:source.frame,unit:'m',quality:'source_precision_not_survey_acceptance',state:'ready',points:[{point_id:source.source+':15',point_index:15,anchor_m:[500000.123456789,4000000.123456789,18.0012345]}]});
test('original row IDs and double precision survive the engineering contract',()=>{
 const result=validateExact(value(),source);assert.equal(result.points[0].point_index,15);assert.equal(result.points[0].anchor_m[0],500000.123456789);
 for(const state of ['preparing','busy','unavailable','narrow_query'])assert.equal(validateExact({...value(),state,points:[]},source).state,state);
});
test('cross-model, frame, stale manifest, display indexes, duplicate and nonfinite coordinates fail closed',()=>{
 for(const mutate of [v=>v.model_id='other',v=>v.space_id='other',v=>v.source_manifest_sha256='c'.repeat(64),v=>v.source_model_sha256='c'.repeat(64),v=>v.frame_id='display',v=>v.state='published',v=>v.points[0].point_id='LOD:15',v=>v.points[0].point_index=.5,v=>v.points[0].anchor_m[0]=Infinity,v=>v.points.push(v.points[0]),v=>v.points[0]=null,v=>v.state='preparing']){const result=value();mutate(result);assert.throws(()=>validateExact(result,source));}
 assert.throws(()=>validateExact({...value(),points:Array(33).fill(value().points[0])},source));
});
