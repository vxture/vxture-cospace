// CLI run-code against local archive-enabled workbench; exactly two archived reports expected.
async (page) => {
  await page.goto('http://127.0.0.1:8772/workbench/');
  const panel = page.locator('#delivery');
  const checks = [];
  const assert = (value, name) => {if (!value) throw new Error(name); checks.push(name);};
  const list = panel.getByRole('button', {name: '读取 / 刷新报告列表'});
  const select = panel.getByRole('combobox', {name: '报告批次'});
  const read = panel.getByRole('button', {name: '读取所选批次'});
  await list.click(); await select.waitFor();
  assert(await select.inputValue() === '' && await read.isDisabled(), 'list_never_auto_selects');
  const options = await select.locator('option').evaluateAll(nodes => nodes.map(n => n.value).filter(Boolean));
  assert(options.length === 2, 'actual_two_report_archive');
  for (const key of options) {
    await select.selectOption(key);
    assert(await panel.getByTestId('delivery-summary').count() === 0, 'selection_clears_previous_summary_' + key.slice(0,8));
    await read.click(); await panel.getByTestId('delivery-generation').waitFor();
    assert((await panel.getByTestId('delivery-generation').innerText()).includes(key.slice(0,36)), 'selected_batch_matches_' + key.slice(0,8));
    assert((await panel.innerText()).includes(key.slice(37)), 'selected_digest_matches_' + key.slice(0,8));
  }
  await panel.screenshot({path: 'output/playwright/delivery-archive/selected.png'});
  await list.click(); await select.waitFor();
  assert(await select.inputValue() === '' && await panel.getByTestId('delivery-summary').count() === 0, 'list_refresh_clears_selection_and_content');
  await select.selectOption(options[0]);
  await page.route('**/delivery-reports/*', route => route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{message:'验证用报告已不可读'}})}));
  await read.click(); await panel.getByRole('alert').waitFor();
  assert(await panel.getByTestId('delivery-summary').count() === 0, 'selected_failure_never_falls_back');
  await page.unroute('**/delivery-reports/*');
  await read.click(); await panel.getByTestId('delivery-summary').waitFor();
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile_selector_no_overflow');
  await panel.screenshot({path:'output/playwright/delivery-archive/mobile.png'});
  await page.setViewportSize({width:1440,height:1100});
  return {checks, test_only:true, authorized:false, injected:['selected report 503']};
}
