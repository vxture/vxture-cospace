import React from 'react';
import productLogo from '../assets/cospace-logo.svg';
import platformLogo from '@vxture/design-system/assets/brands/vx-brand/vxture-logo-icon.svg';

export function CoSpaceBrand({href='/space',label='CoSpace · 我的场景',iconButton=false}:{href?:string;label?:string;iconButton?:boolean}){
 const logo=<img src={productLogo} alt="" width={28} height={28}/>;
 if(iconButton)return <div className="cospace-brand"><a className="cospace-brand-button" href={href} aria-label={label}>{logo}</a><span>CoSpace</span></div>;
 return <a className="cospace-brand" href={href} aria-label={label}>{logo}<span>CoSpace</span></a>;
}

// Public entry pages identify both the platform and its product.
export function PlatformProductBrand(){
 return <div className="platform-product-brand" aria-label="Ruyin · CoSpace"><span className="platform-brand"><img src={platformLogo} alt="" width={24} height={24}/><span>Ruyin</span></span><span className="platform-product-divider" aria-hidden="true"/><CoSpaceBrand href="/space"/></div>;
}
