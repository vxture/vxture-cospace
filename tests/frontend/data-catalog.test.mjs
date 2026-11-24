import {test} from 'node:test';
import assert from 'node:assert/strict';
import {dataResourceNavigation,dataCatalogHref,parseResourceReport} from '../../apps/workbench/src/layout/data-catalog-contract.ts';
import {headerSceneLinkFromUrl} from '../../apps/workbench/src/layout/navigation-contract.ts';

const scope={workspace:'ws-a',project:'',space:'',category:'all'};
const item={key:'one',record_id:'input-one',space_id:'space-one',label:'园区控制网',kind:'input',href:'#data?space=space-one&tab=inputs&input=input-one',resource_id:'resource-'+'a'.repeat(32),source_version:{version_id:'b'.repeat(64),reference_kind:'source_metadata'}};
const report={profile:'cospace.data-resources/0.1',workspace_id:'ws-a',project_id:null,space_id:null,category:'all',items:[item],spaces:[{id:'space-one',name:'园区'}],total:1,status:'ready',source_files_rechecked:false,offset:0,limit:20,next_offset:null};

test('resource navigation is fixed and does not expose workflow actions or projects',()=>{
 assert.deepEqual(dataResourceNavigation.map(s=>s.title),['数据资源','业务记录']);
 assert.deepEqual(dataResourceNavigation.flatMap(s=>s.items.map(i=>i.category)),['all','base','acquisition','reference','result','process']);
 assert.equal(dataCatalogHref(),'/data?scope=all&category=all');
 assert.equal(dataCatalogHref({category:'base',project:'p-one',filter_space:''}),'/data?scope=all&category=base&project=p-one');
 assert.equal(dataCatalogHref({project:'',filter_space:'',search:''}),'/data?scope=all&category=all');
});
test('header scene changes preserve explicit resource filters; scene tools still change their scene',()=>{
 const url=dataCatalogHref({project:'p-one',filter_space:'scene-a',search:'控制网'});
 assert.equal(headerSceneLinkFromUrl('scene-b',url),url);
 assert.equal(headerSceneLinkFromUrl('scene-b','/data?space=scene-a&tab=versions&artifact=old'),'/data?space=scene-b&tab=versions');
});
test('accepts scoped metadata resources and separate process records',()=>{
 assert.equal(parseResourceReport(report,scope).items[0].resource_id,item.resource_id);
 const process={...report,category:'process',items:[{...item,kind:'job',resource_id:null,source_version:null,href:'#build?space=space-one&job=build-one'}]};
 assert.equal(parseResourceReport(process,{...scope,category:'process'}).items[0].resource_id,null);
});
test('rejects cross-workspace, cross-filter and unsafe source links',()=>{
 for(const values of [{workspace_id:'foreign'},{project_id:'other'},{space_id:'other'},{category:'base'}])assert.throws(()=>parseResourceReport({...report,...values},scope));
 for(const values of [{href:'https://external.test/data?space=space-one'},{href:'#build?space=space-one'},{href:'#data?space=other'},{space_id:'foreign'},{resource_id:'invalid'},{source_version:{version_id:'abc'}}])assert.throws(()=>parseResourceReport({...report,items:[{...item,...values}]},scope));
 assert.throws(()=>parseResourceReport({...report,items:[{...item,source_version:{...item.source_version,reference_kind:'verified_payload'}}]},scope));
 assert.throws(()=>parseResourceReport({...report,items:[{...item,kind:'batch'}]},scope));
});
test('partial empty results stay distinguishable from a complete empty directory',()=>{
 const partial=parseResourceReport({...report,status:'partial',items:[],total:0},scope);
 assert.equal(partial.status,'partial');assert.equal(partial.total,0);
});
