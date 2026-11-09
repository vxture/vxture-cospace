export const mapPreferenceKey='cospace.map.preferences.v1';
export type MapPreferences={
 appearance:'follow'|'light'|'dark';
 roads:boolean; buildings:boolean; points:boolean; administrative:boolean; scrollZoom:boolean;
 legend:boolean; autoFit:boolean; directoryExpanded:boolean;
};
export const defaultMapPreferences:MapPreferences={appearance:'follow',roads:true,buildings:true,points:true,administrative:false,scrollZoom:true,legend:true,autoFit:true,directoryExpanded:true};

export function normalizeMapPreferences(value:unknown):MapPreferences{
 const result={...defaultMapPreferences};
 if(!value||typeof value!=='object')return result;
 const saved=value as Record<string,unknown>;
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
