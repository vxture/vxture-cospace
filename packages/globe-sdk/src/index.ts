import {Viewer,Credit,CreditDisplay,HeightReference,BoundingSphere,Cartesian2,Cartesian3,HeadingPitchRange,Matrix4,Color,Math as CesiumMath,ImageryLayer,TileMapServiceImageryProvider,UrlTemplateImageryProvider,ArcGISTiledElevationTerrainProvider,ScreenSpaceEventHandler,ScreenSpaceEventType,Entity,buildModuleUrl} from 'cesium';
import {bindingKey,validateScenes,validateLayers,type GlobeConfiguration,type GlobeScene,type GlobeLayer,type GlobeSelection,type GlobeState,type CameraState,type CameraCommand,type Binding} from './contract';
export * from './contract';
export type GlobeCallbacks={onState?:(state:GlobeState)=>void;onCamera?:(state:CameraState)=>void;onSelect?:(value:GlobeSelection|null)=>void};
export type GlobeController={setScenes:(scenes:GlobeScene[])=>void;setLayers:(layers:GlobeLayer[])=>void;setDisplay:(display:{satellite:boolean;scrollZoom:boolean})=>void;command:(command:CameraCommand)=>void;select:(binding:Binding|null)=>void;resize:()=>void;destroy:()=>void};
export function createGlobe(host:HTMLElement,config:GlobeConfiguration,callbacks:GlobeCallbacks={}):GlobeController{
 if(config.profile!=='vxture.globe-config/0.1'||!config.assetsBaseUrl)throw Error('globe_configuration_invalid');
 (buildModuleUrl as typeof buildModuleUrl & {setBaseUrl:(url:string)=>void}).setBaseUrl(config.assetsBaseUrl);
 // Engine branding is optional; provider attribution remains in CreditDisplay.
 CreditDisplay.cesiumCredit=new Credit('');
 const viewer=new Viewer(host,{baseLayer:ImageryLayer.fromProviderAsync(TileMapServiceImageryProvider.fromUrl(config.assetsBaseUrl.replace(/\/?$/,'/')+'Assets/Textures/NaturalEarthII')),animation:false,timeline:false,baseLayerPicker:false,geocoder:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,fullscreenButton:false,infoBox:false,selectionIndicator:false,requestRenderMode:true});
 viewer.scene.sun.show=false;viewer.scene.moon.show=false;
 if(viewer.scene.skyBox)viewer.scene.skyBox.show=false;
 viewer.scene.backgroundColor=Color.fromCssColorString('#050b17');
 let alive=true,scenes:GlobeScene[]=[],layers:GlobeLayer[]=[],satellite:ImageryLayer|undefined,displaySatellite=true,selected:Binding|null=null;
 const selections=new Map<string,GlobeSelection>();
 let state:GlobeState={ready:true,failure:false,imagery:config.imagery?'satellite':'base',terrain:config.terrain?'loading':'unavailable'};
 function update(change:Partial<GlobeState>){if(alive){state={...state,...change};callbacks.onState?.(state);}}
 function home(fly:boolean){const options={destination:Cartesian3.fromDegrees(105,25,22000000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}};if(fly)viewer.camera.flyTo({...options,duration:1});else viewer.camera.setView(options);}
 const changed=()=>{if(alive)callbacks.onCamera?.({heading:CesiumMath.toDegrees(viewer.camera.heading),tilted:Math.abs(viewer.camera.pitch+Math.PI/2)>.05});};
 const events=new ScreenSpaceEventHandler(viewer.scene.canvas);
 const observer=new ResizeObserver(()=>{if(alive){viewer.resize();viewer.scene.requestRender();}});observer.observe(host);
 try{
 home(false);viewer.camera.changed.addEventListener(changed);viewer.camera.percentageChanged=.01;
 viewer.scene.renderError.addEventListener(()=>update({failure:true}));
 events.setInputAction((event:{position:Cartesian2})=>{const hit=viewer.scene.pick(event.position);callbacks.onSelect?.(hit?.id instanceof Entity?selections.get(String(hit.id.id))||null:null);},ScreenSpaceEventType.LEFT_CLICK);
 if(config.imagery){const provider=new UrlTemplateImageryProvider(config.imagery);satellite=viewer.imageryLayers.addImageryProvider(provider);provider.errorEvent.addEventListener(()=>{if(displaySatellite)update({imagery:'unavailable'});});}
 if(config.terrain)void ArcGISTiledElevationTerrainProvider.fromUrl(config.terrain.url).then(provider=>{if(alive){viewer.terrainProvider=provider;provider.errorEvent.addEventListener(()=>update({terrain:'partial'}));update({terrain:'ready'});viewer.scene.requestRender();}}).catch(()=>update({terrain:'unavailable'}));
 }catch(error){observer.disconnect();events.destroy();viewer.destroy();alive=false;throw error;}
 function redraw(){viewer.entities.removeAll();selections.clear();
 for(const [i,scene] of scenes.entries()){const entity=viewer.entities.add({id:'scene-'+i,name:scene.name,position:Cartesian3.fromDegrees(scene.position[0],scene.position[1],scene.position[2]||0),point:{heightReference:scene.position.length===3?HeightReference.NONE:HeightReference.CLAMP_TO_GROUND,pixelSize:selected&&bindingKey(selected)===bindingKey(scene)?16:10,color:Color.fromCssColorString('#4361ff'),outlineColor:Color.WHITE,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY}});selections.set(entity.id,{spaceId:scene.spaceId,publicationId:scene.publicationId});}
 for(const [i,layer] of layers.entries())for(const [j,feature] of layer.features.entries()){const color=Color.fromCssColorString(layer.color||'#4361ff');const geometry=feature.geometry;const entity=viewer.entities.add({id:`layer-${i}-${j}`,name:feature.name||feature.id,show:layer.visible!==false,...(geometry.type==='point'?{position:Cartesian3.fromDegrees(geometry.position[0],geometry.position[1],geometry.position[2]||0),point:{heightReference:feature.heightMode==='ground'?HeightReference.CLAMP_TO_GROUND:HeightReference.NONE,pixelSize:8,color,outlineColor:Color.WHITE,outlineWidth:1}}:{polyline:{positions:geometry.positions.map(p=>Cartesian3.fromDegrees(p[0],p[1],p[2]||0)),width:3,material:color,clampToGround:feature.heightMode!=='absolute'}})});selections.set(entity.id,{...layer.binding,layerId:layer.id,featureId:feature.id});}
 viewer.scene.requestRender();}
 const controller:GlobeController={
 setScenes(next){if(!alive)return;validateScenes(next);scenes=structuredClone(next);const allowed=new Set(scenes.map(bindingKey));layers=layers.filter(layer=>allowed.has(bindingKey(layer.binding)));redraw();},
 setLayers(next){if(!alive)return;validateLayers(next,scenes);layers=structuredClone(next);redraw();},
 setDisplay(display){if(!alive)return;displaySatellite=display.satellite;if(satellite)satellite.show=display.satellite;viewer.scene.screenSpaceCameraController.enableZoom=display.scrollZoom;update({imagery:display.satellite&&satellite?'satellite':'base'});viewer.scene.requestRender();},
 command(command){if(!alive||state.failure)return;
 viewer.camera.cancelFlight();
 if(command.type==='reset'){home(true);return;}
 if(command.type==='fit'){
  if(!scenes.length)throw new Error('globe_scene_not_available');
  const sphere=BoundingSphere.fromPoints(scenes.map(scene=>Cartesian3.fromDegrees(scene.position[0],scene.position[1],scene.position[2]||0)));
  viewer.camera.flyToBoundingSphere(sphere,{offset:new HeadingPitchRange(0,CesiumMath.toRadians(-50),Math.max(12000,sphere.radius*2.5)),duration:1.5});return;
 }
 if(command.type==='focus'){const scene=scenes.find(item=>bindingKey(item)===bindingKey(command.binding));if(!scene)throw Error('globe_scene_not_available');viewer.camera.flyToBoundingSphere(new BoundingSphere(Cartesian3.fromDegrees(scene.position[0],scene.position[1],scene.position[2]||0),1),{offset:new HeadingPitchRange(0,CesiumMath.toRadians(-50),12000),duration:1.5});return;}
 if(command.type==='zoom-in'||command.type==='zoom-out'){const amount=Math.max(50,viewer.camera.positionCartographic.height*.4);if(command.type==='zoom-in')viewer.camera.zoomIn(amount);else viewer.camera.zoomOut(amount);viewer.scene.requestRender();return;}
 // At the limb or with space in the centre, terrain picking can miss.
 // Keep north/tilt usable by falling back to the ellipsoid, then nadir.
 const center=new Cartesian2(viewer.canvas.clientWidth/2,viewer.canvas.clientHeight/2),ray=viewer.camera.getPickRay(center),target=(ray?viewer.scene.globe.pick(ray,viewer.scene):undefined)||viewer.camera.pickEllipsoid(center,viewer.scene.globe.ellipsoid)||viewer.scene.globe.ellipsoid.scaleToGeodeticSurface(viewer.camera.positionWC);if(!target)return;
 viewer.camera.lookAt(target,new HeadingPitchRange(command.type==='north'?0:viewer.camera.heading,command.type==='north'?viewer.camera.pitch:Math.abs(viewer.camera.pitch+Math.PI/2)>.05?-Math.PI/2:CesiumMath.toRadians(-45),Cartesian3.distance(viewer.camera.positionWC,target)));viewer.camera.lookAtTransform(Matrix4.IDENTITY);viewer.scene.requestRender();changed();},
 select(binding){if(alive){selected=binding;redraw();}},
 resize(){if(alive){viewer.resize();viewer.scene.requestRender();}},
 destroy(){if(!alive)return;alive=false;observer.disconnect();events.destroy();viewer.camera.changed.removeEventListener(changed);viewer.destroy();scenes=[];layers=[];selections.clear();},
 };
 changed();update({ready:true});return controller;
}
