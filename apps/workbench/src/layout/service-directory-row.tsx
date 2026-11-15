import type {ReactNode} from 'react';

export function ServiceDirectoryRow({label,symbol,heading,capabilities,metadata,action}:{
 label:string;symbol:ReactNode;heading:ReactNode;capabilities:ReactNode;metadata:ReactNode;action?:ReactNode;
}){
 return <article className="service-list-row" aria-label={label}>
  <div className="service-entry-symbol" aria-hidden="true">{symbol}</div>
  <div className="service-entry-heading">{heading}</div>
  <div className="service-entry-capability-group">{capabilities}</div>
  <div className="service-entry-release">{metadata}</div>
  {action&&<div className="service-entry-action">{action}</div>}
 </article>;
}
