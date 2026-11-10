import React from 'react';
import {Buildings,Cube} from '@phosphor-icons/react';
import {usePlatformSession} from './platform-auth';
import {useRecordNavigation} from './record-navigation';
import {useSceneDirectory} from './use-scene-directory';

export function HeaderContext(){
 const session=usePlatformSession(),navigation=useRecordNavigation(),{spaces,loading,error}=useSceneDirectory();
 const user=session?.user,organization=user?.org_name||(user?.org_type==='personal'?'个人空间':'组织信息待补全');
 const selected=spaces.find(scene=>scene.id===navigation.space);
 let sceneName='未选择场景';
 if(navigation.space)sceneName=selected?.name||(loading?'读取场景中…':'场景不可用');
 if(error&&navigation.space)sceneName='场景暂不可读';
 return <div className="header-context" aria-label="组织与场景"><span className="header-context-organization" title={organization}><Buildings size={14}/><span>{organization}</span></span><span className="header-context-divider" aria-hidden="true"/><span className="header-context-scene" title={sceneName}><Cube size={14}/><span>{sceneName}</span></span></div>;
}
