export const publicationStates = {
 draft:{label:'草稿',tone:'neutral'},
 ready:{label:'待发布',tone:'info'},
 published:{label:'已发布',tone:'success'},
 disabled:{label:'停用中',tone:'warning'},
 archived:{label:'已归档',tone:'neutral'},
} as const;
// User-space directory preview. All entries are synthetic; no real tenancy or ACL is implied.
export const spaces = [
 {id:'equipment',name:'设备间与相连走廊',level:'一层',version:'V1.1.1',status:'published',updatedAt:'2026-10-27T16:30:00+08:00',objects:['设备柜 A-01','设备柜 A-02','设备柜 B-01'],types:'设备柜',variant:0},
 {id:'pump',name:'水泵设备间',level:'地下一层',version:'V1.2.0',status:'published',updatedAt:'2026-10-26T10:20:00+08:00',objects:['泵组 P-01','泵组 P-02','控制柜 P-03'],types:'设备设施',variant:1},
 {id:'inspection',name:'巡检设备区',level:'二层',version:'V1.1.1',status:'disabled',updatedAt:'2026-10-25T14:10:00+08:00',objects:['检测柜 C-01','检测柜 C-02','检测柜 C-03'],types:'检测设备',variant:2},
] as const;
export function screenHref(id='equipment') {
 return `/space?screen=space&preview=1&space=${encodeURIComponent(id)}`;
}
