import type {LibrarySelection} from '@vxture/ontology-ui';

// See docs/architecture/语义本体业务与配置边界及导航框架-v0.1.md.
// Navigation describes resource collections. Editing and release remain object operations.
export const ontologyResourceNavigation = [{title:'本体资源',items:[
 {category:'all',label:'全部本体',icon:'database'},
 {category:'core',label:'通用核心',icon:'cube'},
 {category:'domain',label:'领域本体',icon:'tree-structure'},
]}] as const;

export function ontologySelectionHref(selection:LibrarySelection,category='all'){
 return '/ontology?'+new URLSearchParams({tab:'library',category,
  ...(selection.moduleId?{module:selection.moduleId}:{}),
  ...(selection.kind?{kind:selection.kind,term:selection.term||''}:{})});
}
