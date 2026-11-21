import {ArrowRight} from '@phosphor-icons/react';
import {Button} from '@vxture/design-system';
import './workflow-next-step.css';

export function WorkflowNextStep({description,label,href,onClick,disabled=false}:Readonly<{description:string;label?:string;href?:string;onClick?:()=>void;disabled?:boolean}>){
 return <footer className="workflow-next-step" aria-label="下一环节"><p>{description}</p>{label&&(href?<Button asChild size="xl"><a href={href}>{label}<ArrowRight size={16}/></a></Button>:<Button size="xl" disabled={disabled} onClick={onClick}>{label}<ArrowRight size={16}/></Button>)}</footer>;
}
