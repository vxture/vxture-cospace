export type AccountProfile={subject:string;display_name:string;org_id:string;workspace_id:string;username?:string;avatar_url?:string;phone?:string;email?:string;phone_verified?:boolean;email_verified?:boolean;org_name?:string;org_short_name?:string;org_logo_url?:string;org_type?:string;workspace_name?:string};

// Display context never changes identity or authorization. Do not invent short names.
export function organizationContext(user?:AccountProfile){
 const fullName=user?.org_name?.trim()||(user?.org_type==='personal'?'个人空间':'组织名称待补全');
 const shortName=user?.org_short_name?.trim()||fullName;
 const workspaceName=user?.workspace_name?.trim()||'工作区名称待补全';
 const typeLabel=({personal:'个人',individual:'个人',organization:'组织',team:'组织',company:'企业'} as Record<string,string>)[user?.org_type||'']||'类型待补全';
 return {fullName,shortName,workspaceName,typeLabel,label:`${shortName} · ${workspaceName}`};
}

export function phoneParts(value:string){
 const compact=value.replace(/[\s()-]/g,''),mainland=/^(?:\+?86)?(1\d{10})$/.exec(compact)?.[1];
 return mainland?{prefix:'+86',number:`${mainland.slice(0,3)} ${mainland.slice(3,7)} ${mainland.slice(7)}`}:{prefix:'',number:value};
}
export function accountVerification(user?:AccountProfile){
 if(user?.phone&&user.phone_verified===true)return {label:'手机已验证',verified:true};
 if(user?.email&&user.email_verified===true)return {label:'邮箱已验证',verified:true};
 return undefined;
}
