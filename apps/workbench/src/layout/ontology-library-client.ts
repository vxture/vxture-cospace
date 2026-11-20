import {parseLibrary,type LibraryClient} from '@vxture/ontology-ui/contract';
import {businessEndpoint} from './business-endpoint';
import {parseDirectory,type DirectoryClient} from '@vxture/ontology-ui/directory-contract';
import {parseWorkbench,type AuthoringClient} from '@vxture/ontology-ui/authoring-contract';

// Host transport adapter. The portable view never imports authentication or scenes.
export const ontologyLibraryClient:LibraryClient={async load(signal){
 const response=await fetch(`${businessEndpoint}/api/ontology-library`,{signal,cache:'no-store'});
 if(!response.ok)throw Error(response.status===401?'请登录后读取本体目录。':response.status===403?'当前身份无法访问本体目录。':'本体目录暂时无法读取，请稍后刷新。');
 return parseLibrary(await response.json());
}};

async function directoryResult(response:Response){
 if(!response.ok){let detail='';try{detail=(await response.json()).detail;}catch{}
  const messages:Record<string,string>={ontology_directory_changed:'目录已变更，请重新读取后继续。',ontology_directory_revision_changed:'归组已被其他人修改，请取消并重新读取目录。',ontology_directory_group_inactive:'所选分组已停用或不存在，请重新读取目录。',ontology_directory_definition_changed:'本体固定版本已变化，请返回目录重新打开。'};
  throw Error(messages[detail]||(response.status===403?'当前身份无权执行此操作。':response.status===401?'请登录后读取本体目录。':'本体目录暂不可用，请重试。'));
 }
 return response.json();
}
const resources=businessEndpoint+'/api/ontology-resources';
export const ontologyDirectoryClient:DirectoryClient={
 list:async(query,signal)=>parseDirectory(await directoryResult(await fetch(resources+'?'+new URLSearchParams(query),{signal,cache:'no-store'}))),
 definition:async(reference,signal)=>parseLibrary(await directoryResult(await fetch(resources+'/definition?'+new URLSearchParams(reference),{signal,cache:'no-store'}))),
 assign:async(change,signal)=>directoryResult(await fetch(resources+'/membership',{method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(change)})),
};

async function authoringResult(response:Response){
 if(!response.ok){let code='';try{code=(await response.json()).detail;}catch{}
  const messages:Record<string,string>={revision_changed:'草稿已被其他人修改，请保留本地内容后重新打开。',review_stale:'审批已过期，请重新校验并送审。',self_approval_forbidden:'提交人不能审批自己的定义。',release_not_found:'依赖尚未发布，或固定版本不存在。请先发布准确版本的依赖。',validation_failed:'草稿校验未通过，请修正后再送审。',version_exists:'此版本已发布，请推进版本号。',version_not_advanced:'新版本必须高于已发布版本。',approval_required:'请先取得当前修订的审批。',request_conflict:'请求标识冲突，请重新打开后操作。'};
  throw Error(messages[code]||(response.status===403?'当前身份无权执行此操作。':response.status===401?'请先登录。':'编制服务暂不可用，请重试。'));
 }return response.json();
}
const definitions=businessEndpoint+'/api/ontology-definitions';
export const ontologyAuthoringClient:AuthoringClient={
 read:async(moduleId,signal)=>parseWorkbench(await authoringResult(await fetch(definitions+'?'+new URLSearchParams({module_id:moduleId}),{signal,cache:'no-store'}))),
 change:async(body,signal)=>authoringResult(await fetch(definitions,{method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})),
 definition:async(reference,signal)=>authoringResult(await fetch(definitions+'?'+new URLSearchParams(reference),{signal,cache:'no-store'})),
 review:async(reviewId,signal)=>authoringResult(await fetch(definitions+'?'+new URLSearchParams({review_id:reviewId}),{signal,cache:'no-store'})),
};
