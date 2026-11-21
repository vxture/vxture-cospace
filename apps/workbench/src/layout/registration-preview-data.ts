// Presentation calculations only. The host must independently validate and
// recompute the candidate before any future approval or geographic consumption.
export type Point3=[number,number,number];
export type ControlPoint={id:string;purpose:'fit'|'check';source_m:Point3;target_m:Point3;evidence_ref:string};
export type RegistrationInput={profile:string;synthetic:boolean;source:{space_id:string;candidate_id:string;manifest_sha256:string;model_sha256:string;frame_id:string;unit:string;axes:string[];handedness:string;bounds_m:[Point3,Point3]};target:{frame_id:string;title:string;kind:string;horizontal_reference:string;definition_ref:string;evidence_ref:string;unit:string;axes:string;vertical_reference:string;geographic_adapter:'not_connected'};method:'provided_rigid_3d';direction:'source_to_target';matrix:number[][];controls:ControlPoint[];check_limits:{horizontal_m:number;vertical_m:number}};
export type ControlResidual=ControlPoint&{predicted_m:Point3;delta_m:Point3;horizontal_m:number;vertical_m:number;within_limits:boolean};
export function transformRegistrationPoint(point:Point3,matrix:number[][]):Point3{
 return matrix.slice(0,3).map(row=>row[0]*point[0]+row[1]*point[1]+row[2]*point[2]+row[3]) as Point3;
}
export function registrationPreview(input:RegistrationInput){
 const controls:ControlResidual[]=input.controls.map(point=>{
  const predicted=transformRegistrationPoint(point.source_m,input.matrix),delta=predicted.map((n,i)=>n-point.target_m[i]) as Point3;
  const horizontal=Math.hypot(delta[0],delta[1]),vertical=Math.abs(delta[2]);
  return {...point,predicted_m:predicted,delta_m:delta,horizontal_m:horizontal,vertical_m:vertical,within_limits:horizontal<=input.check_limits.horizontal_m&&vertical<=input.check_limits.vertical_m};
 });
 const check=controls.filter(p=>p.purpose==='check');
 const rms=(values:number[])=>Math.sqrt(values.reduce((sum,n)=>sum+n*n,0)/values.length);
 return {controls,passed:check.length>0&&check.every(p=>p.within_limits),horizontal_rmse_m:rms(check.map(p=>p.horizontal_m)),vertical_rmse_m:rms(check.map(p=>p.vertical_m)),max_horizontal_m:Math.max(...check.map(p=>p.horizontal_m)),max_vertical_m:Math.max(...check.map(p=>p.vertical_m))};
}
export type RegistrationPreview=ReturnType<typeof registrationPreview>;
export function displayMetres(value:number){return value.toFixed(3);}
