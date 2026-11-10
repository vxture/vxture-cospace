import React,{useState} from 'react';
import {ShellUserMenu,ShellPreferencePanel,useTheme} from '@vxture/design-system';
import {usePlatformSession} from './platform-auth';
import {phoneParts,accountVerification} from './account-profile';

export function ProductUserMenu({onLogout}:{onLogout:()=>void|Promise<void>}){
 const session=usePlatformSession(),{mode,setMode,density,setDensity,fontSize,setFontSize}=useTheme();
 const [error,setError]=useState('');
 const user=session?.user,phone=user?.phone?phoneParts(user.phone):null;
 return <ShellUserMenu openLabel="账户菜单" contentClassName="cospace-user-panel" user={{displayName:user?.display_name||'交付工程师',avatarSrc:user?.avatar_url,avatarAlt:user?.display_name,avatarFallback:Array.from(user?.display_name||'工')[0],statusTag:session?accountVerification(user):{label:'设计预览',verified:false},meta:<span className="account-contact-lines">{phone&&<span><span className="account-phone-prefix">{phone.prefix}</span>{phone.number}</span>}{user?.email&&<span>{user.email}</span>}</span>}}
  links={[{key:'account',label:'账号中心',href:'https://accounts.vxture.com',icon:'user',newTab:true}]}
  settings={<ShellPreferencePanel locale="zh-CN" localeOptions={[{locale:'zh-CN',label:'简体中文',nativeName:'简体中文'}]} onLocaleChange={()=>{}} theme={mode} onThemeChange={setMode} density={density} onDensityChange={setDensity} fontSize={fontSize} onFontSizeChange={setFontSize} labels={{title:'偏好设置',locale:'语言',theme:'主题',density:'密度',fontSize:'字号',themeOptions:{system:'系统',light:'亮色',dark:'暗色'},densityOptions:{compact:'紧凑',default:'默认',comfortable:'宽松'},fontSizeOptions:{small:'小',default:'默认',large:'大'}}}/>}
  extras={error?<p role="alert" className="text-body-small text-destructive">{error}</p>:undefined}
  actions={[{key:'switch',label:'切换用户',icon:'users',onClick:()=>location.assign('/auth/login?returnTo=%2Fspace&selectAccount=true')},{key:'logout',label:session?'退出登录':'退出 UI 预览',icon:'sign-out',danger:true,onClick:async()=>{setError('');try{await onLogout();}catch{setError('退出暂未完成，请稍后重试。');}}}]}/>;
}
