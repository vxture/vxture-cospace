async (page) => {
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await page.setViewportSize({width:1600,height:1050});
  await page.goto('http://127.0.0.1:8766/workbench/layout.html');
  const checks=[];
  const assert=(condition,name)=>{if(!condition)throw new Error(name);checks.push(name);};
  await page.locator('.object[data-object="1"]').click();
  assert(await page.locator('#object-name').innerText()==='设备柜 A-02','object_selection');
  await page.locator('#search').fill('B-01');
  assert(await page.locator('.object:visible').count()===1,'object_filter');
  await page.locator('#search').fill('');
  await page.locator('[data-layer="unknown"]').click();
  assert(!await page.locator('#unknown').isVisible(),'layer_toggle');
  await page.locator('[data-layer="unknown"]').click();
  await page.locator('#agent').click();
  assert(await page.locator('#agent-overlay').isVisible(),'agent_preview_switch');
  await page.locator('#human').click();
  await page.locator('[data-inspect="evidence"]').click();
  assert(await page.locator('#evidence').isVisible(),'evidence_panel');
  await page.locator('[data-inspect="attributes"]').click();
  await page.locator('.object[data-object="0"]').click();
  await page.screenshot({path:'output/playwright/layout/space.png',fullPage:true});
  for(const name of ['data','ontology','build','delivery']){
    await page.locator(`[data-page="${name}"]`).click();
    assert(await page.locator('#module').isVisible()&&!await page.locator('#spatial').isVisible(),'workspace_'+name);
  }
  await page.screenshot({path:'output/playwright/layout/delivery.png',fullPage:true});
  await page.locator('[data-page="space"]').click();
  await page.locator('#version').click();
  assert(await page.locator('#dialog').isVisible(),'version_dialog');
  await page.locator('#dialog-close').click();
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile_no_overflow');
  await page.screenshot({path:'output/playwright/layout/mobile.png',fullPage:true});
  await page.setViewportSize({width:1600,height:1050});
  assert(errors.length===0,'no_javascript_errors');
  return {checks,illustration_only:true};
}
