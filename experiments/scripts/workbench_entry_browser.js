async page=>{
 await page.context().route('**/workbench/**',r=>r.continue({headers:{...r.request().headers(),'Cache-Control':'no-cache'}}));
 await page.goto('http://127.0.0.1:8766/workbench/layout.html?revision=cardbutton32#data');
 if(await page.locator('#enter-preview').isVisible())await page.locator('#enter-preview').click();
 const sizes=await page.locator('.launcher-control').evaluate(e=>{const b=e.getBoundingClientRect(),s=e.querySelector('svg').getBoundingClientRect();return {width:b.width,height:b.height,icon:s.width};});if(sizes.width!==40||sizes.height!==40||sizes.icon!==20)throw Error(JSON.stringify(sizes));
 const first=await page.locator('header button,header a').first().getAttribute('aria-label');if(first!=='功能 Launcher')throw Error('Launcher is not first header action');
 await page.getByRole('button',{name:'功能 Launcher',exact:true}).click();
 await page.getByRole('link',{name:'我的空间',exact:false}).click();
 await page.getByRole('heading',{name:'我的空间',exact:true}).waitFor();
 if(!await page.getByRole('button',{name:'停用中，不可打开'}).isDisabled())throw Error('Disabled space');
 if(await page.locator('.space-card-preview svg').count()!==3)throw Error('Preview images');
 const buttonHeights=await page.locator('.space-card-open').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().height));if(buttonHeights.some(h=>h!==32))throw Error(JSON.stringify(buttonHeights));
 const ids=await page.locator('.space-card-preview [id]').evaluateAll(es=>es.map(e=>e.id));if(new Set(ids).size!==ids.length)throw Error('Duplicate SVG IDs');
 await page.setViewportSize({width:919,height:902});await page.screenshot({path:'output/playwright/layout/space-directory-images.png',animations:'disabled'});
 const meta=await page.locator('.space-card-footer').first().evaluate(e=>{const v=e.querySelector('span').getBoundingClientRect(),t=e.querySelector('time').getBoundingClientRect();return {inline:Math.abs(v.top-t.top)<2,text:e.textContent};});if(!meta.inline||!meta.text.includes('版本：V1.1.1')||!meta.text.includes('打开空间'))throw Error(JSON.stringify(meta));
 const original=page.url(),newPage=page.context().waitForEvent('page');await page.locator('.space-card-preview').first().click();
 const screen=await newPage;await screen.waitForLoadState();if(!screen.url().includes('screen=space')||page.url()!==original)throw Error('Screen entry');await screen.close();
 return {launcherToDirectory:true,threePreviews:true,uniqueSvgIds:true,newTabPreservesDirectory:true};
}
