// Separate UI acceptance for the four reports produced by delivery_acceptance.
// Serve those reports and the existing workbench on loopback port 8774.
async (page) => {
  await page.goto('http://127.0.0.1:8774/workbench/');
  const checks = [];
  const assert = (value, id) => {if (!value) throw new Error(id); checks.push({id, passed:true});};
  const panel = page.locator('#delivery');
  const list = panel.getByRole('button', {name:'读取 / 刷新报告列表'});
  const select = panel.getByRole('combobox', {name:'报告批次'});
  const read = panel.getByRole('button', {name:'读取所选批次'});
  const target = 'http://127.0.0.1:8774/scenes/synthetic-equipment-corridor/releases/release-spatial-sample-001/delivery-reports';
  const listing = await (await page.request.get(target)).json();
  assert(listing.items.length === 4, 'ui.four_generated_reports');
  await list.click(); await select.waitFor();
  assert(await select.inputValue() === '' && await read.isDisabled(), 'ui.explicit_selection_required');
  for (const item of listing.items) {
    await select.selectOption(item.report_key);
    assert(await panel.getByTestId('delivery-summary').count() === 0, 'ui.selection_clears.' + item.report_id);
    await read.click(); await panel.getByTestId('delivery-generation').waitFor();
    const actual = await (await page.request.get(target + '/' + item.report_key)).json();
    const report = actual.report;
    assert((await panel.getByTestId('delivery-generation').innerText()).includes(item.report_id) &&
      (await panel.innerText()).includes(item.sha256), 'ui.fixed_identity.' + item.report_id);
    const text = await panel.getByTestId('delivery-summary').innerText();
    assert(text.includes(item.needs_attention ? '需要处理' : '报告内无待处理项'), 'ui.diagnostic_matches.' + item.report_id);
    const codes = [...new Set(report.findings.map(f => f.code))];
    for (const code of codes) assert((await panel.locator('.delivery-findings').innerText()).includes(code), 'ui.reason_displayed.' + item.report_id + '.' + code);
    assert((await panel.innerText()).includes('机器人运行授权：未授予'), 'ui.no_authority.' + item.report_id);
    if (codes.includes('proof_fields_missing')) await panel.screenshot({path:'output/playwright/delivery-acceptance/missing-grant.png'});
  }
  await list.click(); await select.waitFor();
  assert(await select.inputValue() === '' && await panel.getByTestId('delivery-summary').count() === 0, 'ui.refresh_resets_selection_and_report');
  await page.getByRole('textbox',{name:'场景 ID',exact:true}).fill('different-scene');
  assert(await panel.getByRole('combobox').count() === 0, 'ui.scene_change_clears_list');
  await list.click(); await select.waitFor();
  assert(await select.locator('option').count() === 1 && await read.isDisabled(), 'ui.wrong_scene_no_fallback');
  return {test_only:true, passed:true, checks, browser_executed:true, authorized:false, production_accepted:false};
}
