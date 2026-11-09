import React,{useState} from 'react';
import {ArrowsOutSimple,House} from '@phosphor-icons/react';
import {Button,ShellThemeToggle,ShellLocaleSwitcher,useTheme} from '@vxture/design-system';
import {usePublicLocale,setPublicLocale} from './public-locale';

export function PublicHeaderTools(){
 const {theme,setTheme}=useTheme();
 const locale=usePublicLocale();
 const [error,setError]=useState('');
 const fullscreen=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();setError('');}catch{setError('当前浏览器不支持全屏显示');}};
 return <><div className="public-header-tools" role="group" aria-label="主题、语言、全屏与主站"><ShellThemeToggle currentTheme={theme} onThemeChange={setTheme} buttonLabel="切换主题"/><ShellLocaleSwitcher currentLocale={locale} options={[{locale:"zh-CN",label:"简体中文",nativeName:"简体中文"},{locale:"en",label:"English",nativeName:"English"}]} onLocaleChange={setPublicLocale} buttonLabel="语言"/><Button variant="ghost" size="icon-md" aria-label="全屏显示" onClick={fullscreen}><ArrowsOutSimple size={16}/></Button><Button variant="ghost" size="icon-md" asChild><a href="https://vxture.com" target="_blank" rel="noopener noreferrer" aria-label="VXTURE 主站（新标签页）"><House size={16}/></a></Button></div>{error&&<span role="status" className="text-label-small">{error}</span>}</>;
}
