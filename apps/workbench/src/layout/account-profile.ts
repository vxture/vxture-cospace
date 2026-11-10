export type AccountProfile={subject:string;display_name:string;org_id:string;workspace_id:string;username?:string;avatar_url?:string;phone?:string;email?:string;phone_verified?:boolean;email_verified?:boolean;org_name?:string;org_type?:string;workspace_name?:string};

export function phoneParts(value:string){
 const compact=value.replace(/[\s()-]/g,''),mainland=/^(?:\+?86)?(1\d{10})$/.exec(compact)?.[1];
 return mainland?{prefix:'+86',number:`${mainland.slice(0,3)} ${mainland.slice(3,7)} ${mainland.slice(7)}`}:{prefix:'',number:value};
}
export function accountVerification(user?:AccountProfile){
 if(user?.phone&&user.phone_verified===true)return {label:'手机已验证',verified:true};
 if(user?.email&&user.email_verified===true)return {label:'邮箱已验证',verified:true};
 return undefined;
}
