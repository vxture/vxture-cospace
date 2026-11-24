export const referenceFileAccept='.pdf,.png,.jpg,.jpeg,.csv,.txt,.ifc';
export function referenceFileError(file:Pick<File,'name'|'size'>){
 if(!file.size||file.size>32*1024*1024)return '请选择不超过 32 MiB 的非空文件。';
 if(file.name!==file.name.trim()||file.name.length>160||/[\\/:<>"|?*\u0000-\u001f\u007f]/.test(file.name)||/[. ]$/.test(file.name)||!referenceFileAccept.split(',').some(ext=>file.name.toLowerCase().endsWith(ext)))return '支持 PDF、图片、CSV、TXT 和 IFC，请检查文件名称与格式。';
 return '';
}
export function fileUploadQuery(values:{ownerKind:string;project:string;name:string;base:boolean;reason:string;requestId:string}){
 return new URLSearchParams({owner_kind:values.ownerKind,...(values.ownerKind==='project'?{owner_project_id:values.project}:{}),name:values.name,is_base:String(values.base),reason:values.reason,request_id:values.requestId,expected_revision:'0'});
}
