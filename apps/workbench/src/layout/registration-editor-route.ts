// Both surfaces bind the same explicit, fixed model. Never inherit a model from
// the active scene, an opener window or a previously selected candidate.
export function registrationEditorTarget(url:string){
 const [path,search='']=url.split('?'),params=new URLSearchParams(search);
 if(path!=='/registration'||params.get('mode')!=='edit')return null;
 return {space:params.get('space')||'',job:params.get('job')||''};
}
export function registrationSurfaceHref(space:string,job:string,editing=false){
 const params=new URLSearchParams({space,job});
 if(editing)params.set('mode','edit');
 return '/registration?'+params;
}
