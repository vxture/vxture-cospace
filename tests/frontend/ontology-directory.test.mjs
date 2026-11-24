import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseDirectory} from '../../packages/ontology-ui/src/directory-contract.ts';
import {ontologyResourceNavigation,ontologySelectionHref} from '../../apps/workbench/src/layout/ontology-navigation-contract.ts';

const page=()=>({profile:'vxture.ontology-directory/0.1',snapshot:'a'.repeat(64),page:1,page_size:10,total:1,can_group:false,groups:[{group_id:'preset-water',name:'给排水',status:'active'}],items:[{reference:{module_id:'water',version:'0.1.0',sha256:'b'.repeat(64)},title:'给排水',description:'定义',layer:'domain',status:'draft',concept_count:3,relation_count:0,revision:0,group_ids:['preset-water']}]});
test('directory validates compact summaries and membership references',()=>{
 assert.equal(parseDirectory(page()).items[0].title,'给排水');
 for(const mutate of [v=>v.items[0].group_ids.push('missing'),v=>v.items.push(v.items[0]),v=>v.page_size=1000,v=>v.can_group='true',v=>v.items[0].revision=-1,v=>v.items[0].reference.sha256='bad']){const v=page();mutate(v);assert.throws(()=>parseDirectory(v));}
});
test('directory stays portable and consumes injected transport',()=>{
 const view=readFileSync('packages/ontology-ui/src/directory.tsx','utf8');
 assert.ok(!view.includes('fetch('));assert.ok(!view.includes('react-router'));
 assert.ok(!view.includes('business-endpoint'));
 assert.match(view,/completeLibrary=\{false\}/);
});

test('ontology navigation retains resource collections and keeps workflow actions inside an ontology',()=>{
 assert.deepEqual(ontologyResourceNavigation,[{title:'本体资源',items:[
  {category:'all',label:'全部本体',icon:'database'},
  {category:'core',label:'通用核心',icon:'cube'},
  {category:'domain',label:'领域本体',icon:'tree-structure'},
 ]}]);
 const sidebar=readFileSync('apps/workbench/src/layout/ontology-navigation.tsx','utf8');
 assert.match(sidebar,/ontologyResourceNavigation\.map/);
 assert.doesNotMatch(sidebar,/label:['"](?:展示|查看|编辑|发布|系统配置)['"]/);
 const workspace=readFileSync('apps/workbench/src/layout/shared-ontology.tsx','utf8');
 assert.match(workspace,/renderDetail=\{library=><DefinitionWorkspace/);
});

test('resource navigation opens collections and object links retain the same collection',()=>{
 for(const {category} of ontologyResourceNavigation.flatMap(section=>section.items)){
  const collection=new URL(ontologySelectionHref({moduleId:''},category),'https://cospace.test');
  assert.equal(collection.pathname,'/ontology');
  assert.deepEqual([...collection.searchParams],[['tab','library'],['category',category]]);
  const detail=new URL(ontologySelectionHref({moduleId:'water',kind:'concept',term:'pump'},category),'https://cospace.test');
  assert.deepEqual([...detail.searchParams],[['tab','library'],['category',category],['module','water'],['kind','concept'],['term','pump']]);
 }
});
