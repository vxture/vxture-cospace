async page=>{
 await page.context().route('**/workbench/**',r=>r.continue({headers:{...r.request().headers(),'Cache-Control':'no-cache'}}));
 await page.setViewportSize({width:1440,height:1000});
 await page.goto('http://127.0.0.1:8766/workbench/layout.html?screen=space&preview=1&space=equipment&revision=aligned32#space');
 if(await page.getByRole('button',{name:'沉浸展示',exact:true}).count())throw Error('Immersive button remains');
 await page.getByRole('button',{name:'全屏',exact:true}).waitFor();
 await page.getByRole('group',{name:'显示图层',exact:true}).waitFor();
 const inspect=()=>page.evaluate(()=>{const rect=s=>document.querySelector(s).getBoundingClientRect();const t=rect('.space-tools'),g=rect('[aria-label="显示图层"]'),f=g.bottom;const picker=rect('.space-picker');return {toolbarHeight:t.height,toolbarWidth:t.width,layerLeft:g.left,layerRight:g.right,layerBottom:f,switchWidth:rect(".space-layer-switch").width,switchHeight:rect(".space-layer-switch").height,width:innerWidth,height:innerHeight,noOverflow:document.documentElement.scrollWidth<=innerWidth,noTopOverlap:picker.right<t.left,hasLayerCard:!!document.querySelector('[aria-label="显示图层板块"]')};});
 const alignment=await page.evaluate(()=>{const r=s=>document.querySelector(s).getBoundingClientRect(),a=r('.space-action-group'),v=r('.space-avatar-control'),buttons=[...document.querySelectorAll('.space-tools button,.space-title-control')].map(e=>e.getBoundingClientRect().height);return {heights:buttons,groupGap:parseFloat(getComputedStyle(document.querySelector('.space-action-group')).gap),avatarGap:v.left-a.right};});if(alignment.heights.some(h=>h!==32)||alignment.groupGap!==4||alignment.avatarGap!==16)throw Error(JSON.stringify(alignment));
 const desktop=await inspect();if(desktop.toolbarHeight>48||desktop.hasLayerCard||!desktop.noTopOverlap||desktop.layerLeft!==24||desktop.switchWidth!==24||desktop.switchHeight!==16)throw Error(JSON.stringify(desktop));
 await page.getByRole('switch',{name:'坐标网格',exact:true}).click();if(!await page.locator('#grid').isVisible())throw Error('Grid toggle');
 await page.getByRole('button',{name:'当前人视图，切换到机视图',exact:true}).click();if(!await page.locator('#agent-overlay').isVisible())throw Error('Agent view');
 await page.getByRole('button',{name:'用户账户',exact:true}).click();await page.getByText('设计预览身份 · 非真实登录',{exact:true}).waitFor();await page.keyboard.press('Escape');
 await page.screenshot({path:'output/playwright/layout/corner-controls.png',animations:'disabled'});
 await page.setViewportSize({width:390,height:844});const mobile=await inspect();if(!mobile.noOverflow||!mobile.noTopOverlap||mobile.layerLeft!==24||mobile.layerRight>390||mobile.layerBottom>844)throw Error(JSON.stringify(mobile));
 await page.screenshot({path:'output/playwright/layout/corner-controls-mobile.png',animations:'disabled'});
 return {alignment,desktop,mobile,layerSwitch:true,viewSwitch:true};
}
