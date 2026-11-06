async page=>{
 const checks=[],errors=[];page.on('pageerror',e=>errors.push(e.message));const ok=(v,n)=>{if(!v)throw Error(n);checks.push(n);};
 await page.context().route('**/workbench/**',r=>r.continue({headers:{...r.request().headers(),'Cache-Control':'no-cache'}}));
 await page.setViewportSize({width:1440,height:1000});await page.goto('http://127.0.0.1:8766/workbench/layout.html?screen=space&preview=1&space=equipment&revision=rails#space');await page.locator('#spatial').waitFor();
 ok(await page.locator('header').count()===0,'no_header');ok(await page.locator('#spatial').evaluate(e=>e.getBoundingClientRect().height===innerHeight),'full_viewport');
 await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:'output/playwright/layout/refined-space.png',fullPage:true,animations:'disabled'});
 ok(await page.locator('.space-rail-left').getAttribute('inert')!==null,'closed_rail_inert');
 await page.getByRole('button',{name:'展开或收起左侧信息栏',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.space-rail-left').getAttribute('data-open')==='true');
 ok((await page.locator('.space-rail-left').innerText()).includes('示例 v0.1'),'description_in_device_rail');
 await page.getByRole('button',{name:'设备对象',exact:true}).click();ok(!await page.getByRole('textbox',{name:'搜索空间对象'}).isVisible(),'device_block_folds');ok(await page.getByRole('switch',{name:'未知区域'}).isVisible(),'layer_block_independent');await page.getByRole('button',{name:'设备对象',exact:true}).click();await page.getByRole('button',{name:'显示图层',exact:true}).click();ok(!await page.getByRole('switch',{name:'未知区域'}).isVisible(),'layer_block_folds');ok(await page.getByRole('textbox',{name:'搜索空间对象'}).isVisible(),'device_block_independent');await page.getByRole('button',{name:'显示图层',exact:true}).click();
 await page.locator('.space-rail-left').getByRole('button',{name:'设备柜 A-02',exact:true}).click();await page.locator('.device-detail').waitFor();
 await page.waitForFunction(()=>parseFloat(document.querySelector('.device-detail').style.left)>0);
 const bounds=await page.evaluate(()=>{const a=document.querySelector('[data-object="1"]').getBoundingClientRect(),b=document.querySelector('.device-detail').getBoundingClientRect();return {gap:Math.min(Math.abs(b.left-a.right),Math.abs(a.left-b.right)),left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:innerWidth,height:innerHeight};});
 ok(bounds.gap<40,'detail_near_device');ok(bounds.left>=0&&bounds.right<=bounds.width&&bounds.top>=0&&bounds.bottom<=bounds.height,'detail_within_viewport');
 ok(await page.locator('#labels text').nth(1).getAttribute('visibility')==='hidden','selected_label_unified_with_detail');
 await page.screenshot({path:'output/playwright/layout/refined-device.png',fullPage:true,animations:'disabled'});
 await page.getByRole('button',{name:'空间概览',exact:true}).click();ok(await page.locator('.space-rail-right').getAttribute('data-open')==='true','right_rail_open');
 await page.getByRole('button',{name:'关闭属性面板'}).click();await page.screenshot({path:'output/playwright/layout/refined-rails.png',fullPage:true,animations:'disabled'});
 await page.getByRole('button',{name:'展开或收起左侧信息栏',exact:true}).click();ok(await page.locator('.space-rail-left').getAttribute('inert')!==null,'rail_folds_with_inert');
 await page.getByRole('button',{name:'空间概览',exact:true}).click();await page.locator('.pick[data-object="2"]').click();await page.locator('.device-detail').waitFor();await page.getByRole('tab',{name:'来源与证据'}).click();ok((await page.locator('.device-detail').innerText()).includes('质量证据'),'evidence_tab');await page.getByRole('button',{name:'关闭属性面板'}).click();
 await page.getByRole('button',{name:'切换空间'}).click();await page.getByRole('button',{name:/水泵设备间/}).click();await page.waitForFunction(()=>location.search.includes('space=pump'));ok(await page.locator('.device-detail').count()===0,'space_switch_clears_detail');
 await page.locator('.pick[data-object="0"]').click();await page.locator('.device-detail').waitFor();
 await page.setViewportSize({width:390,height:844});await page.waitForFunction(()=>{const b=document.querySelector('.device-detail').getBoundingClientRect();return b.right<=innerWidth&&b.bottom<=innerHeight;});ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile_no_overflow');await page.screenshot({path:'output/playwright/layout/refined-mobile.png',fullPage:true,animations:'disabled'});await page.getByRole('button',{name:'关闭属性面板'}).click();
 await page.getByRole('button',{name:'沉浸展示',exact:true}).click();ok(!await page.getByRole('toolbar').isVisible(),'immersive');await page.keyboard.press('Escape');await page.getByRole('toolbar').waitFor();
 await page.setViewportSize({width:1440,height:1000});ok(errors.length===0,'no_javascript_errors');return {checks,bounds,errors};
}
