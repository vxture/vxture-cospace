import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseDirectory} from '../../packages/ontology-ui/src/directory-contract.ts';

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
