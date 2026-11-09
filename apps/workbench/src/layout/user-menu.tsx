import React,{useState} from 'react';
import {ShellUserMenu,ShellPreferencePanel,useTheme} from '@vxture/design-system';
import {usePlatformSession} from './platform-auth';

export function ProductUserMenu({onLogout}:{onLogout:()=>void|Promise<void>}){
 const session=usePlatformSession(),{mode,setMode,density,setDensity,fontSize,setFontSize}=useTheme();
 const [error,setError]=useState('');
 return <ShellUserMenu openLabel="账户菜单" contentClassName="cospace-user-panel" user={{displayName:session?.user?.display_name||'交付工程师',avatarFallback:session?.user?.display_name?.slice(0,1)||'工',uniqueLine:session?.user?.subject||'设计预览身份',meta:'CoSpace · Ruyin 平台账号',statusTag:{label:session?'平台已登录':'设计预览',verified:false}}}
  links={[{key:'account',label:'账号中心',href:'https://accounts.vxture.com/account',icon:'user'}]}
  settings={<ShellPreferencePanel locale="zh-CN" localeOptions={[{locale:'zh-CN',label:'简体中文',nativeName:'简体中文'}]} onLocaleChange={()=>{}} theme={mode} onThemeChange={setMode} density={density} onDensityChange={setDensity} fontSize={fontSize} onFontSizeChange={setFontSize} labels={{title:'偏好设置',locale:'语言',theme:'主题',density:'密度',fontSize:'字号',themeOptions:{system:'系统',light:'亮色',dark:'暗色'},densityOptions:{compact:'紧凑',default:'默认',comfortable:'宽松'},fontSizeOptions:{small:'小',default:'默认',large:'大'}}}/>}
  extras={error?<p role="alert" className="text-body-small text-destructive">{error}</p>:undefined}
  actions={[{key:'switch',label:'切换用户',icon:'users',onClick:()=>location.assign('/auth/login?returnTo=%2Fspace&selectAccount=true')},{key:'logout',label:session?'退出登录':'退出 UI 预览',icon:'sign-out',danger:true,onClick:async()=>{setError('');try{await onLogout();}catch{setError('退出暂未完成，请稍后重试。');}}}]}/>;
}
