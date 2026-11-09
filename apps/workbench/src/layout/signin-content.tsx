import {usePublicLocale} from './public-locale';
import React from 'react';
import {ArrowRight,ShieldCheck} from '@phosphor-icons/react';
import {Button} from '@vxture/design-system';
import {UnifiedAccountCard} from './unified-account-card';

export function SignInContent({onLogin}:{onLogin:()=>void}){
 const en=usePublicLocale()==='en'; return <div className="home-signin-content"><div className="home-login-heading"><p>WELCOME TO COSPACE</p><h1>{en?'Spatial Intelligence Service':'空间态势服务'}</h1></div><div className="home-login-actions"><UnifiedAccountCard/><Button className="home-login-cta" id="third-party-login" onClick={onLogin}>{en?'Continue to sign in':'继续登录'}<ArrowRight size={16} aria-hidden="true"/></Button></div><p className="home-login-security"><ShieldCheck size={16} aria-hidden="true"/>{en?'Sign in securely with your platform account':'使用平台账号安全登录'}</p></div>;
}
