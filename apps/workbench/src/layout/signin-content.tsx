import {usePublicLocale} from './public-locale';
import React from 'react';
import {ArrowRight} from '@phosphor-icons/react';
import {Button} from '@vxture/design-system';
import {UnifiedAccountCard} from './unified-account-card';
import {SpatialMotif} from './spatial-motif';
import {PublicEntryHeading,PublicEntryFootnote} from './public-entry-parts';

export function SignInContent({onLogin}:{onLogin:()=>void}){
 const en=usePublicLocale()==='en'; return <div className="home-signin-content"><PublicEntryHeading>{en?'Spatial Intelligence Service':'空间态势服务'}</PublicEntryHeading><div className="home-login-illustration"><SpatialMotif className="home-login-motif"/></div><div className="home-login-actions"><UnifiedAccountCard/><Button className="home-login-cta" id="third-party-login" onClick={onLogin}>{en?'Continue to sign in':'继续登录'}<ArrowRight size={16} aria-hidden="true"/></Button></div><PublicEntryFootnote/></div>;
}
