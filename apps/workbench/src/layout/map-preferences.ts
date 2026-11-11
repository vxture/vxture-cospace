export const mapPreferenceKey='cospace.map.preferences.v1';
export type MapPreferences={
 appearance:'follow'|'light'|'dark';
 basemap:'standard'|'satellite'; viewMode:'2D'|'3D';
 roads:boolean; buildings:boolean; points:boolean; administrative:boolean; scrollZoom:boolean;
 legend:boolean; autoFit:boolean; directoryExpanded:boolean;
};
export const defaultMapPreferences:MapPreferences={appearance:'dark',basemap:'standard',viewMode:'2D',roads:true,buildings:true,points:false,administrative:true,scrollZoom:true,legend:true,autoFit:true,directoryExpanded:true};

export function normalizeMapPreferences(value:unknown):MapPreferences{
 const result={...defaultMapPreferences};
 if(!value||typeof value!=='object')return result;
 const saved=value as Record<string,unknown>;
 if(saved.basemap==='standard'||saved.basemap==='satellite')result.basemap=saved.basemap;
 if(saved.viewMode==='2D'||saved.viewMode==='3D')result.viewMode=saved.viewMode;
 if(['follow','light','dark'].includes(String(saved.appearance)))result.appearance=saved.appearance as MapPreferences['appearance'];
 for(const key of ['roads','buildings','points','administrative','scrollZoom','legend','autoFit','directoryExpanded'] as const){
  if(typeof saved[key]==='boolean')result[key]=saved[key];
 }
 return result;
}
export function readMapPreferences():MapPreferences{
 try{return normalizeMapPreferences(JSON.parse(localStorage.getItem(mapPreferenceKey)||'null'));}
 catch{return {...defaultMapPreferences};}
}
export function mapIsDark(preferences:MapPreferences,theme:'light'|'dark'){
 return preferences.appearance==='follow'?theme==='dark':preferences.appearance==='dark';
}
export function mapFeatures(preferences:MapPreferences){
 return ['bg',...(preferences.roads?['road']:[]),...(preferences.buildings?['building']:[]),...(preferences.points?['point']:[])];
}
