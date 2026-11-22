import test from 'node:test';
import assert from 'node:assert/strict';
import {validateDisplay} from '../../apps/workbench/src/layout/model-display-contract.ts';

const source='a'.repeat(64),manifest='b'.repeat(64),id='c'.repeat(64);
const ref={space:'space-one',kind:'candidate',identity:'build-one'};
const value=()=>({model:{id:'build-one',space_id:'space-one',unit:'m',members:{'spatial.npz':{sha256:source}},human_view:{source_model_sha256:source},agent_view:{source_model_sha256:source},construction:{model_points:100}},display:{profile:'cospace.model-display/0.1',provider:'potree/1.8.2',id,state:'ready',source_manifest_sha256:manifest,source_model_sha256:source,origin_m:[500000,600000,100],model_to_display:[[1,0,0],[0,0,1],[0,-1,0]],point_count:100,encoding_error_m:.00001,entry:`/candidates/build-one/display/${id}/metadata.json`}});

test('metadata readiness does not require downloading geometry or computation',()=>{
 const scene=validateDisplay(value(),ref);
 assert.equal(scene.display.state,'ready');
 assert.equal(scene.positions.length,0);assert.equal(scene.agent_points.length,0);
});
test('cross-scene, source, URL, count and numeric precision mismatches fail closed',()=>{
 const mutations=[v=>v.model.space_id='space-other',v=>v.model.agent_view.source_model_sha256='e'.repeat(64),v=>v.display.entry='https://other.example/model.json',v=>v.display.point_count=10,v=>v.display.encoding_error_m=.01,v=>v.display.origin_m[0]=Infinity,v=>v.display.model_to_display[0]=[2,0,0],v=>v.display.state='published'];
 for(const mutate of mutations){const v=value();mutate(v);assert.throws(()=>validateDisplay(v,ref));}
});
test('fixed publication binds model, source and manifest; candidate cannot impersonate it',()=>{
 const v=value(),publication='preview-'+'d'.repeat(16);
 v.model.publication={id:publication,space_id:'space-one',candidate_id:'build-one',source_model_sha256:source,model_manifest_sha256:manifest};
 v.display.entry=`/publications/${publication}/display/${id}/metadata.json`;
 const fixed={...ref,kind:'publication',identity:publication};
 assert.equal(validateDisplay(v,fixed).model.id,'build-one');
 v.model.publication.model_manifest_sha256='f'.repeat(64);
 assert.throws(()=>validateDisplay(v,fixed));
});
