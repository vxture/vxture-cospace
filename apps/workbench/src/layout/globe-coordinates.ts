// Cesium uses WGS84. Do not interpret GCJ02 or unvalidated positions as WGS84.
export function globePosition(location?:{longitude:number;latitude:number;crs:string}):[number,number]|null{
 if(!location||location.crs!=='WGS84'||!Number.isFinite(location.longitude)||!Number.isFinite(location.latitude)||Math.abs(location.longitude)>180||Math.abs(location.latitude)>90)return null;
 return [location.longitude,location.latitude];
}
