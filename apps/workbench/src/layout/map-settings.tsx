import React,{useState} from 'react';
import {Button,SegmentedControl,Popover,PopoverTrigger,PopoverContent,Switch,useTheme} from '@vxture/design-system';
import {SlidersHorizontal,X,ArrowCounterClockwise} from '@phosphor-icons/react';
import type {MapPreferences} from './map-preferences';
function MapChoiceCards({kind,value,onChange}:{kind:'basemap'|'view';value:string;onChange:(value:string)=>void}){
 const items=kind==='basemap'?[{value:'standard',label:'标准地图'},{value:'satellite',label:'卫星影像'}]:[{value:'2D',label:'2D'},{value:'3D',label:'3D'}];
 return <div className="scene-map-choice-grid" role="radiogroup" aria-label={kind==='basemap'?'底图类型':'视图模式'}>{items.map(item=><button type="button" role="radio" aria-checked={item.value===value} tabIndex={item.value===value?0:-1} onClick={()=>onChange(item.value)} onKeyDown={event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?items[0]:event.key==='End'?items[1]:items.find(option=>option.value!==item.value)!;onChange(next.value);const buttons=event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role=radio]');buttons?.[items.indexOf(next)]?.focus();}}} key={item.value} className="scene-map-choice">
  <svg className={'scene-map-choice-preview scene-map-preview-'+item.value} viewBox="0 0 100 48" aria-hidden="true">
   {kind==='basemap'?(item.value==='standard'?<>
    <path fill="#e9eee6" d="M0 0h100v48H0z"/>
    <path fill="#c7dfb7" d="m0 0 27 0-8 16L0 22zm74 29 26-7v26H76z"/>
    <path fill="#b7d9ee" d="M67-3C48 9 72 17 58 28S49 42 56 51h10c-12-14 0-18 7-25S62 9 78-3Z"/>
    <path fill="none" stroke="#d2c5a9" strokeWidth="7" d="m-5 37 110-24M31-5l8 58"/>
    <path fill="none" stroke="#fff" strokeWidth="4" d="m-5 37 110-24M31-5l8 58"/>
    <path fill="none" stroke="#fff" strokeWidth="2" d="m0 12 55 1m-7 35-1-29M80 0l7 48M5 0l12 48"/>
    <path fill="#d0d4d4" d="m20 18 8-2 2 9-8 2zm21-13 9-1 1 7-9 1zm3 18 8-2 1 6-8 2zm-22 17 10-2 1 7-10 2zm54-8 7-2 2 10-7 2z"/>
   </>:<>
    <path fill="#485e39" d="M0 0h100v48H0z"/>
    <path fill="#6f7946" d="m0 0 26 0-9 20L0 16zm62 1 38 0v15l-31 5z"/>
    <path fill="#82905a" d="m0 30 22-7 15 25H0zm72 2 28-11v27H79z"/>
    <path fill="#364c31" d="m3 2 15 4-8 7zm17 2 8 3-6 9zm57 1 19 3-9 7zM5 35l12-4 7 13H8zM81 36l14-6 5 14-15 2z"/>
    <path fill="#395b65" d="M64-3C47 9 68 18 55 28s-7 15-2 23h9c-11-14 0-19 7-26S60 9 75-3Z"/>
    <path fill="none" stroke="#b5afa0" strokeWidth="3" d="m-5 37 110-24M31-5l8 58"/>
    <path fill="none" stroke="#d5cabb" strokeWidth="1" d="m-5 37 110-24M31-5l8 58"/>
    <path fill="#2c332e" d="m15 18 11-2 2 9-11 2zm25-10 10-2 2 8-10 2zm3 22 9-2 2 8-9 2zm-24 9 10-2 2 8-10 2z"/>
    <path fill="#b0ada0" d="m14 16 10-2 2 8-10 2zm25-10 10-2 2 8-10 2zm3 22 9-2 2 7-9 2zm-24 9 10-2 2 7-10 2z"/>
   </>):item.value==='2D'?<><path className="map-preview-grid" d="M10 8h80v32H10zm0 16h80M30 8v32M50 8v32M70 8v32"/><path className="map-preview-building" d="M33 13h30v22H33z"/></>:<><path className="map-preview-grid" d="m5 31 45-22 45 22-45 16zM27 20l45 22M27 42l45-22"/><path className="map-preview-building" d="m34 17 16-8 16 8v18l-16 8-16-8zm0 0 16 8 16-8M50 25v18"/></>}
  </svg><span>{item.label}</span>
 </button>)}</div>;
}

export function MapSettings({preferences,updatePreference,onViewChange,viewMode,onReset,layerError='',administrativeError='',preferenceError=''}:{preferences:MapPreferences;updatePreference:<K extends keyof MapPreferences>(key:K,value:MapPreferences[K])=>void;onViewChange:(value:'2D'|'3D')=>void;viewMode:'2D'|'3D';onReset:()=>void;layerError?:string;administrativeError?:string;preferenceError?:string}){
 const [settingsOpen,setSettingsOpen]=useState(false);const {theme}=useTheme();
 return <>   <Popover open={settingsOpen} onOpenChange={setSettingsOpen}><PopoverTrigger asChild><Button size="icon-xl" variant="ghost" aria-label="地图设置" aria-pressed={settingsOpen}><SlidersHorizontal size={14}/></Button></PopoverTrigger><PopoverContent side="left" align="end" sideOffset={10} className="scene-map-settings" data-ui-theme={theme} aria-label="地图设置"><header><h2><SlidersHorizontal size={16}/>地图设置</h2><Button size="icon-xl" variant="ghost" aria-label="关闭地图设置" onClick={()=>setSettingsOpen(false)}><X size={14}/></Button></header><div className="scene-map-settings-columns"><section className="scene-map-appearance" aria-label="底图外观"><h3>地图主题</h3><fieldset className="map-theme-fieldset" disabled={viewMode==='3D'} title={viewMode==='3D'?'三维地球保留影像原色':undefined}><SegmentedControl size="md" className="h-control-xl" fill ariaLabel="地图主题" value={preferences.appearance} onChange={value=>updatePreference('appearance',value as MapPreferences['appearance'])} items={[{value:'follow',label:'跟随全局'},{value:'light',label:'亮色'},{value:'dark',label:'暗色'}]}/></fieldset><h3>底图类型</h3><MapChoiceCards kind="basemap" value={preferences.basemap} onChange={value=>updatePreference('basemap',value as MapPreferences['basemap'])}/><h3>视图模式</h3><MapChoiceCards kind="view" value={viewMode} onChange={value=>onViewChange(value as '2D'|'3D')}/></section><div className="scene-map-settings-options"><section aria-label="地图要素"><h3>地图要素</h3>{([['administrative','省级行政边界'],['roads','道路'],['buildings','建筑物'],['points','兴趣点（POI）']] as const).map(([key,label])=><label className="scene-map-setting-row" key={key} htmlFor={'map-setting-'+key}><span>{label}</span><Switch id={'map-setting-'+key} disabled={viewMode==='3D'&&['administrative','roads','buildings','points','autoFit'].includes(key)} checked={preferences[key]} onCheckedChange={value=>updatePreference(key,value)}/></label>)}{layerError&&<p role="alert">{layerError}</p>}{administrativeError&&<p role="alert">{administrativeError}</p>}</section><section aria-label="交互与显示"><h3>交互与显示</h3>{([['scrollZoom','滚轮缩放'],['autoFit','筛选后自动取景'],['legend','场景状态图例']] as const).map(([key,label])=><label className="scene-map-setting-row" key={key} htmlFor={'map-setting-'+key}><span>{label}</span><Switch id={'map-setting-'+key} disabled={viewMode==='3D'&&['administrative','roads','buildings','points','autoFit'].includes(key)} checked={preferences[key]} onCheckedChange={value=>updatePreference(key,value)}/></label>)}</section></div></div><footer><span role="alert">{preferenceError}</span><Button size="sm" variant="ghost" onClick={()=>onReset()}><ArrowCounterClockwise size={12}/>恢复默认</Button></footer></PopoverContent></Popover></>;
}
