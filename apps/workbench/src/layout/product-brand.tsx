import React from 'react';
import productLogo from '../assets/cospace-logo.svg';
import platformLogo from '@vxture/design-system/assets/brands/vx-brand/vxture-logo-icon.svg';

export function CoSpaceBrand({href='#space'}:{href?:string}){
 return <a className="cospace-brand" href={href} aria-label="CoSpace · 我的场景"><img src={productLogo} alt="" width={28} height={28}/><span>CoSpace</span></a>;
}

export function LauncherPlatformBrand(){
 return <div className="launcher-platform-brand"><img src={platformLogo} alt="" width={24} height={24}/><span>Ruyin</span></div>;
}

// Public entry pages identify both the platform and its product.
export function PlatformProductBrand(){
 return <div className="platform-product-brand" aria-label="Ruyin · CoSpace"><span className="platform-brand"><img src={platformLogo} alt="" width={24} height={24}/><span>Ruyin</span></span><span className="platform-product-divider" aria-hidden="true"/><CoSpaceBrand href="/workbench/layout.html#space"/></div>;
}
