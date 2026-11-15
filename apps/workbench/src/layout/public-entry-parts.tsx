import React from 'react';
import {ShieldCheck} from '@phosphor-icons/react';
import {usePublicLocale} from './public-locale';

export function PublicEntryHeading({children}:{readonly children:React.ReactNode}){
 return <header className="home-login-heading"><p>WELCOME TO COSPACE</p><h1>{children}</h1></header>;
}

export function PublicEntryFootnote({children}:{readonly children?:React.ReactNode}){
 const en=usePublicLocale()==='en';
 return <footer className="entry-footnote"><ShieldCheck size={16} aria-hidden="true"/><span>{children||(en?'Sign in securely with your platform account':'使用平台账号安全登录')}</span></footer>;
}
