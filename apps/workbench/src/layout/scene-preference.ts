// This is a display/navigation preference, never an authorization decision.
export const scenePreferenceKey=(scope:string)=>`cospace.scene-selection:${scope}`;
export function preferredScene(explicit:string|null,remembered:string){return explicit===null?remembered:explicit;}
export function sceneContextHref(url:string,scene:string){
 const [path,search='']=url.split('?'),params=new URLSearchParams(search);
 // Catalog entry stays a catalog even when the header remembers a scene.
 if(!scene||path==='/'||path==='/space'||params.has('space'))return url;
 params.set('space',scene);return `${path}?${params}`;
}
