// Horizontal conversion never implies a vertical datum conversion.
export function globePosition(location?:{longitude:number;latitude:number;crs:string;altitude?:number;altitude_reference?:string}):[number,number,number?]|null{
 if(!location||location.crs!=='WGS84'||!Number.isFinite(location.longitude)||!Number.isFinite(location.latitude)||Math.abs(location.longitude)>180||Math.abs(location.latitude)>90)return null;
 if(location.altitude_reference==='ellipsoid'&&location.altitude!=null){
  if(!Number.isFinite(location.altitude)||location.altitude< -12000||location.altitude>100000)return null;
  return [location.longitude,location.latitude,location.altitude];
 }
 return [location.longitude,location.latitude];
}
