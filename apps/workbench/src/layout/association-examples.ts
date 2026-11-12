// The retired screens were synthetic illustrations, with no measured geometry.
// Preserve their object intent as editable templates; never manufacture anchors.
export const associationExamples=[
 {id:'equipment',name:'设备间与相连走廊',level:'一层',objects:[
  {id:'equipment-a01',name:'设备柜 A-01',type:'cabinet'},
  {id:'equipment-a02',name:'设备柜 A-02',type:'cabinet'},
  {id:'equipment-b01',name:'设备柜 B-01',type:'cabinet'},
 ]},
 {id:'pump',name:'水泵设备间',level:'地下一层',objects:[
  {id:'pump-p01',name:'泵组 P-01',type:'pump'},
  {id:'pump-p02',name:'泵组 P-02',type:'pump'},
  {id:'pump-p03',name:'控制柜 P-03',type:'control_cabinet'},
 ]},
 {id:'inspection',name:'巡检设备区',level:'二层',objects:[
  {id:'inspection-c01',name:'检测柜 C-01',type:'inspection_cabinet'},
  {id:'inspection-c02',name:'检测柜 C-02',type:'inspection_cabinet'},
  {id:'inspection-c03',name:'检测柜 C-03',type:'inspection_cabinet'},
 ]},
] as const;
export function associationExample(id:string|null){return associationExamples.find(item=>item.id===id);}
export function legacyExampleHref(url:string){
 const [path,search='']=url.split('?'),params=new URLSearchParams(search);
 const example=associationExample(params.get('space'));
 if(path!=='/space'||params.get('screen')!=='space'||params.has('publication')||!example)return null;
 // Explicitly clear scene context: a synthetic ID is never an authorized scene.
 return '/association?'+new URLSearchParams({space:'',tab:'objects',example:example.id});
}
