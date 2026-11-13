type Row={failed:number;rejected:number;partial:boolean;configuration:string};
type Status={label:string;tone:'neutral'|'brand'|'warning'|'danger'};
// Confirmed errors outrank incomplete coverage; absence of evidence is not health.
export function homeMonitorStatus(rows:Row[],loading:boolean,errors:number):Status{
 if(loading)return {label:'核对中',tone:'neutral'};
 if(rows.some(row=>row.failed>0||row.configuration==='unavailable'))return {label:'异常',tone:'danger'};
 if(rows.some(row=>row.rejected>0))return {label:'请求受阻',tone:'warning'};
 if(!rows.length)return {label:'不可读',tone:'neutral'};
 if(errors>0||rows.some(row=>row.partial))return {label:'待核验',tone:'neutral'};
 if(rows.some(row=>row.configuration!=='configured'))return {label:'待配置',tone:'neutral'};
 return {label:'正常',tone:'brand'};
}
