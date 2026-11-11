import {createGlobe,type GlobeLayer} from '@vxture/globe';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import './style.css';

// Deliberately synthetic. Never register these fixtures as a real CoSpace scene.
const host=document.querySelector<HTMLElement>('#globe')!;
const status=document.querySelector<HTMLOutputElement>('#status')!;
const binding={spaceId:'example-synthetic-scene',publicationId:'example-fixed-publication'};
const api=createGlobe(host,{profile:'vxture.globe-config/0.1',assetsBaseUrl:'/assets/cesium/'},{
 onState:state=>{status.value=state.failure?'渲染失败':'就绪';},
 onSelect:selection=>{status.value=selection?JSON.stringify(selection):'未选择';},
});
api.setScenes([{...binding,name:'合成测试场景',position:[116,40]}]);
const layers:GlobeLayer[]=[
 {id:'ground-agent',binding,color:'#26c6a5',features:[{id:'ground-track',heightMode:'ground',geometry:{type:'line',positions:[[115.98,39.99],[116,40],[116.02,40.01]]}}]},
 {id:'air-agent',binding,color:'#ffbd59',features:[{id:'air-track',heightMode:'absolute',geometry:{type:'line',positions:[[115.98,40.01,1000],[116,40,1500],[116.02,39.99,1000]]}}]},
];
function draw(){
 const ground=document.querySelector<HTMLInputElement>('#ground')!.checked;
 const air=document.querySelector<HTMLInputElement>('#air')!.checked;
 api.setLayers(layers.map((layer,index)=>({...layer,visible:index===0?ground:air})));
}
draw();api.command({type:'focus',binding});
document.querySelector('#fit')!.addEventListener('click',()=>api.command({type:'focus',binding}));
document.querySelector('#north')!.addEventListener('click',()=>api.command({type:'north'}));
document.querySelector('#reset')!.addEventListener('click',()=>api.command({type:'reset'}));
document.querySelector('#ground')!.addEventListener('change',draw);
document.querySelector('#air')!.addEventListener('change',draw);
window.addEventListener('pagehide',()=>api.destroy(),{once:true});
