export const GLOBE_PROTOCOL='vxture.globe/0.1' as const;
export const SDK_VERSION='0.2.0';
export const CESIUM_VERSION='1.147.0';
export type Position=[number,number,number?];
export type Binding={spaceId:string;publicationId?:string};
export type HeightMode='ground'|'absolute';
export type GlobeScene=Binding&{name:string;position:Position};
export type GlobeFeature={id:string;name?:string;heightMode?:HeightMode;geometry:{type:'point';position:Position}|{type:'line';positions:Position[]}};
export type GlobeLayer={id:string;binding:Binding;visible?:boolean;color?:string;features:GlobeFeature[]};
export type GlobeSelection=Binding&{layerId?:string;featureId?:string};
export type CameraCommand={type:'reset'|'fit'|'north'|'tilt'|'zoom-in'|'zoom-out'}|{type:'focus';binding:Binding};
export type GlobeState={ready:boolean;failure:boolean;imagery:'base'|'satellite'|'unavailable';terrain:'loading'|'ready'|'unavailable'|'partial'};
export type CameraState={heading:number;tilted:boolean};
export type GlobeConfiguration={profile:'vxture.globe-config/0.1';assetsBaseUrl:string;imagery?:{url:string;credit:string;maximumLevel:number};terrain?:{url:string}};
export function bindingKey(binding:Binding){return JSON.stringify([binding.spaceId,binding.publicationId??null]);}
export function validBinding(value:unknown):value is Binding{
 if(!value||typeof value!=='object'||Array.isArray(value))return false;
 const v=value as Binding;return typeof v.spaceId==='string'&&v.spaceId.length>0&&v.spaceId.length<=160&&(v.publicationId===undefined||typeof v.publicationId==='string'&&v.publicationId.length>0&&v.publicationId.length<=160);
}
export function validPosition(value:unknown):value is Position{
 return Array.isArray(value)&&(value.length===2||value.length===3)&&value.every(n=>typeof n==='number'&&Number.isFinite(n))&&Math.abs(value[0])<=180&&Math.abs(value[1])<=90&&(value.length===2||Math.abs(value[2])<=100000000);
}
export function validateScenes(scenes:GlobeScene[]){
 if(!Array.isArray(scenes)||scenes.length>10000)throw Error('globe_scene_budget');
 const seen=new Set<string>();for(const scene of scenes){if(!validBinding(scene)||typeof scene.name!=='string'||scene.name.length>256||!validPosition(scene.position)||seen.has(bindingKey(scene)))throw Error('invalid_globe_scene');seen.add(bindingKey(scene));}
}
export function validateLayers(layers:GlobeLayer[],scenes:GlobeScene[]){
 if(!Array.isArray(layers)||layers.length>100)throw Error('globe_layer_budget');
 const allowed=new Set(scenes.map(bindingKey)),ids=new Set<string>();let points=0;
 for(const layer of layers){if(!layer||typeof layer.id!=='string'||!layer.id||layer.id.length>160||ids.has(layer.id)||!validBinding(layer.binding)||!allowed.has(bindingKey(layer.binding))||!Array.isArray(layer.features)||layer.visible!==undefined&&typeof layer.visible!=='boolean'||layer.color!==undefined&&!/^#[0-9a-f]{6}$/i.test(layer.color))throw Error('invalid_globe_layer');ids.add(layer.id);const features=new Set<string>();
 for(const feature of layer.features){if(!feature||typeof feature.id!=='string'||!feature.id||feature.id.length>160||features.has(feature.id)||feature.name!==undefined&&(typeof feature.name!=='string'||feature.name.length>256)||!feature.geometry)throw Error('invalid_globe_feature');features.add(feature.id);
 if(feature.heightMode!==undefined&&!['ground','absolute'].includes(feature.heightMode))throw new Error('invalid_height_mode');
 const geometry=feature.geometry;if(geometry.type==='point'){if(!validPosition(geometry.position))throw Error('invalid_globe_position');points++;}else if(geometry.type==='line'){if(!Array.isArray(geometry.positions)||geometry.positions.length<2||!geometry.positions.every(validPosition))throw Error('invalid_globe_line');points+=geometry.positions.length;}else throw Error('unsupported_globe_geometry');
 if(points>50000)throw Error('globe_feature_budget');}}
}
export type EmbedCommand={protocol:typeof GLOBE_PROTOCOL;requestId:string;command:CameraCommand};
// Parent messages cannot supply credentials, provider URLs, arbitrary coordinates or data layers.
export function parseEmbedCommand(value:unknown):EmbedCommand|null{
 if(!value||typeof value!=='object'||Array.isArray(value))return null;const v=value as EmbedCommand;
 if(Object.keys(v).some(k=>!['protocol','requestId','command'].includes(k))||v.protocol!==GLOBE_PROTOCOL||typeof v.requestId!=='string'||!v.requestId||v.requestId.length>80||!v.command||typeof v.command!=='object'||Array.isArray(v.command))return null;
 const c=v.command;
 if(c.type==='focus'){if(Object.keys(c).some(k=>!['type','binding'].includes(k))||!validBinding(c.binding)||Object.keys(c.binding).some(k=>!['spaceId','publicationId'].includes(k)))return null;}
 else if(!['reset','fit','north','tilt','zoom-in','zoom-out'].includes(c.type)||Object.keys(c).length!==1)return null;
 return v;
}
export function trustedParent(event:{origin:string;source:unknown},parent:unknown,parentOrigin:string){return event.source===parent&&event.origin===parentOrigin;}
