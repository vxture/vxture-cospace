import {usePublicLocale} from './public-locale';
import React from 'react';
import {User} from '@phosphor-icons/react';

export function UnifiedAccountCard(){
 const en=usePublicLocale()==='en'; return <div className="home-unified-account"><User size={24} aria-hidden="true"/><div><strong>{en?'One unified account':'全局统一账号'}</strong><p>{en?'Your account, organization and workspace, connected':'账号、单位与工作空间，一处连接'}</p></div></div>;
}
