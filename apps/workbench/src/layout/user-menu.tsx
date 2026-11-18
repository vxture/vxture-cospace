import React,{useState} from 'react';
import {ShellUserMenu,ShellPreferencePanel,useTheme} from '@vxture/design-system';
import {usePlatformSession} from './platform-auth';
import {displayText} from './display-text';

export function ProductUserMenu({onLogout}:{onLogout:()=>void|Promise<void>}){
 const session=usePlatformSession(),{mode,setMode,density,setDensity,fontSize,setFontSize}=useTheme();
 const [error,setError]=useState('');
 const user=session?.user,name=displayText(user?.display_name,'当前用户');
 return <ShellUserMenu openLabel="账户菜单" contentClassName="cospace-user-panel" user={{displayName:name,avatarSrc:user?.avatar_url,avatarAlt:name,avatarFallback:Array.from(name)[0],meta:displayText(user?.username,'')}}
  links={[{key:'account',label:'个人信息',href:'/account',icon:'user'}]}
  settings={<ShellPreferencePanel locale="zh-CN" localeOptions={[{locale:'zh-CN',label:'简体中文',nativeName:'简体中文'}]} onLocaleChange={()=>{}} theme={mode} onThemeChange={setMode} density={density} onDensityChange={setDensity} fontSize={fontSize} onFontSizeChange={setFontSize} labels={{title:'偏好设置',locale:'语言',theme:'主题',density:'密度',fontSize:'字号',themeOptions:{system:'系统',light:'亮色',dark:'暗色'},densityOptions:{compact:'紧凑',default:'默认',comfortable:'宽松'},fontSizeOptions:{small:'小',default:'默认',large:'大'}}}/>}
  extras={error?<p role="alert" className="text-body-small text-destructive">{error}</p>:undefined}
  actions={[{key:'switch',label:'切换用户',icon:'users',onClick:()=>location.assign('/auth/login?returnTo=%2Fspace&selectAccount=true')},{key:'logout',label:session?'退出登录':'退出 UI 预览',icon:'sign-out',danger:true,onClick:async()=>{setError('');try{await onLogout();}catch{setError('退出暂未完成，请稍后重试。');}}}]}/>;
}
