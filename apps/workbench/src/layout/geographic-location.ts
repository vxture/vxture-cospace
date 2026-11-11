export type GeographicLocation={longitude:number;latitude:number;altitude?:number;crs:'WGS84'|'GCJ02';altitude_reference?:'unknown'|'ellipsoid'|'orthometric';source?:string};
export function validLocation(location?:GeographicLocation|null):location is GeographicLocation{
 return !!location&&Number.isFinite(location.longitude)&&Math.abs(location.longitude)<=180&&Number.isFinite(location.latitude)&&Math.abs(location.latitude)<=90&&['WGS84','GCJ02'].includes(location.crs);
}
export function locationLabel(location?:GeographicLocation|null){
 if(!location)return '位置未登记';
 if(!validLocation(location))return '坐标无效';
 return location.crs==='GCJ02'?'已登记 · 三维坐标待转换':'已登记';
}
export function altitudeLabel(location?:GeographicLocation|null){
 if(location?.altitude==null)return '未登记';
 const reference=({ellipsoid:'椭球高',orthometric:'海拔',unknown:'基准未明确'})[location.altitude_reference||'unknown'];
 return `${location.altitude} m · ${reference}`;
}
export function locationFromDraft(draft:{longitude:string;latitude:string;altitude:string;crs:GeographicLocation['crs'];reference:NonNullable<GeographicLocation['altitude_reference']>;source:string}):GeographicLocation|null{
 const lon=draft.longitude.trim(),lat=draft.latitude.trim(),height=draft.altitude.trim();
 if(!lon&&!lat&&!height)return null;
 if(!lon||!lat)throw new Error('请同时填写经度和纬度。');
 const value:GeographicLocation={longitude:Number(lon),latitude:Number(lat),crs:draft.crs};
 if(!validLocation(value))throw new Error('经纬度超出有效范围。');
 if(height){
  const altitude=Number(height);
  if(!Number.isFinite(altitude)||altitude< -12000||altitude>100000)throw new Error('高度应为 −12000 至 100000 米。');
  value.altitude=altitude;value.altitude_reference=draft.reference;
 }
 if(draft.source.trim())value.source=draft.source.trim();
 return value;
}
