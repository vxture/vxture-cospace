import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseLibrary,matchingModules,exportLibrary} from '../../packages/ontology-ui/src/contract.ts';
import {headerSceneLinkFromUrl} from '../../apps/workbench/src/layout/navigation-contract.ts';
import {sceneContextHref} from '../../apps/workbench/src/layout/scene-preference.ts';

const source=JSON.parse(readFileSync('packages/ontology/kernel/definitions.json','utf8'));
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v;}
const sha=v=>createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
const library=()=>({profile:'vxture.ontology-catalog/0.1',status:'draft',library_sha256:sha(source),capabilities:['definition-validation','dependency-resolution','definition-export'],modules:source.modules.map(definition=>({reference:{module_id:definition.module_id,version:definition.version,sha256:sha(definition)},definition:structuredClone(definition)}))});

test('shared drafts validate without scene or workspace and export dependency closure',()=>{
 const value=parseLibrary(library());assert.equal(value.modules.length,8);
 assert.deepEqual(exportLibrary(value,'electrical').modules.map(m=>m.module_id),['core','electrical']);
 const exported=exportLibrary(value);assert.equal(exported.profile,'vxture.ontology-library/0.1');assert.equal(exported.modules.length,8);
 assert.equal(matchingModules(value,'core','').length,1);
 assert.deepEqual(matchingModules(value,'domain','额定电压').map(v=>v.reference.module_id),['electrical']);
 assert.equal(matchingModules(value,'','unknown definition').length,0);
 assert.throws(()=>exportLibrary(value,'missing'));
});

test('unsupported or inconsistent responses never appear as a usable library',()=>{
 for(const mutate of [
  v=>v.status='published',
  v=>v.profile='cospace.preview-ontology/0.2',
  v=>v.capabilities.push('instance-validation'),
  v=>v.modules.push(v.modules[0]),
  v=>v.modules[1].reference.version='9.0.0',
  v=>v.modules.find(e=>e.definition.module_id==='electrical').definition.requires[0].sha256='0'.repeat(64),
  v=>v.modules=v.modules.filter(e=>e.definition.module_id!=='core'),
  v=>v.modules[0].definition.concepts.entity.parent='core:physical_object',
  v=>v.modules.find(e=>e.definition.module_id==='electrical').definition.concepts.distribution_cabinet.parent='water:pump',
  v=>v.modules.find(e=>e.definition.module_id==='electrical').definition.concepts.distribution_cabinet.properties.rated_voltage.data_type='string',
 ]){const value=library();mutate(value);assert.throws(()=>parseLibrary(value));}
 assert.throws(()=>parseLibrary(null));assert.throws(()=>parseLibrary({...library(),modules:[]}));
});

test('scene picker does not reset public ontology view or add scene scope',()=>{
 assert.equal(sceneContextHref('/ontology?tab=library','remembered'),'/ontology?tab=library');
 assert.equal(headerSceneLinkFromUrl('other','/ontology?tab=library'),'/ontology?tab=library');
 assert.equal(headerSceneLinkFromUrl('other','/ontology?tab=rules&ontology_id=old'),'/ontology?tab=rules&ontology_id=old');
});

test('portable view has no product router, platform, scene or endpoint imports',()=>{
 const view=readFileSync('packages/ontology-ui/src/library.tsx','utf8');
 const imports=[...view.matchAll(/from ['"]([^'"]+)['"]/g)].map(v=>v[1]);
 assert.deepEqual(imports.sort(),['./contract','@phosphor-icons/react','@vxture/design-system','react'].sort());
 assert.ok(!view.includes('fetch('));
 const nav=readFileSync('apps/workbench/src/layout/product-navigation.ts','utf8');
 assert.match(nav,/title:'公共资源'.*route:'ontology'/);
});
