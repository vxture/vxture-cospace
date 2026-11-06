// Pass this function to playwright-cli run-code after opening the local workbench.
// The server must expose the clean saved report. Fault/delay cases below are browser routes.
async (page) => {
  const results = [];
  const panel = page.locator('#delivery');
  const button = panel.getByRole('button', {name: '读取 / 刷新交付报告'});
  const summary = panel.getByTestId('delivery-summary');
  const assert = (value, label) => {if (!value) throw new Error(label); results.push(label);};
  await button.click();
  await summary.waitFor();
  assert((await summary.innerText()).includes('报告内无待处理项'), 'actual_saved_clean_report');
  await panel.getByText('完整版本绑定与组件状态', {exact: true}).click();
  assert(await panel.locator('dt').count() === 10, 'all_ten_binding_fields');
  assert((await panel.innerText()).includes('字段齐备，未验证'), 'proof_presence_never_promotes_validity');
  await panel.screenshot({path: 'output/playwright/delivery/clean.png'});
  const routePattern = '**/delivery';
  await page.route(routePattern, route => route.fulfill({status: 503, contentType: 'application/json',
    body: JSON.stringify({detail: {message: '验证用报告不可读'}})}));
  await button.click();
  await panel.getByRole('alert').waitFor();
  assert(await summary.count() === 0, 'mocked_failure_clears_previous_summary');
  await page.unroute(routePattern);
  await button.click(); await summary.waitFor();
  for (const name of ['场景 ID', '发布 ID']) {
    let releaseRoute;
    const blocked = new Promise(resolve => {releaseRoute = resolve;});
    await page.route(routePattern, async route => {
      await blocked;
      await route.fulfill({status: 503, contentType: 'application/json',
        body: JSON.stringify({detail: {message: '旧目标迟到响应'}})}).catch(() => {});
    });
    await button.click();
    await panel.getByText('正在读取，旧报告已清除。', {exact: true}).waitFor();
    assert(await summary.count() === 0, `refresh_clears_immediately_before_${name}`);
    const input = page.getByRole('textbox', {name, exact: true});
    const original = await input.inputValue();
    await input.fill('different-target');
    releaseRoute();
    await panel.getByText('尚未读取交付核对报告。', {exact: true}).waitFor();
    assert(await summary.count() === 0 && await panel.getByRole('alert').count() === 0,
      `delayed_old_response_ignored_after_${name}`);
    await page.unroute(routePattern);
    await input.fill(original);
    await button.click(); await summary.waitFor();
  }
  await page.getByRole('textbox', {name: '场景 ID', exact: true}).fill('different-scene');
  await button.click(); await panel.getByRole('alert').waitFor();
  assert((await panel.getByRole('alert').innerText()).includes('报告与指定场景或发布不一致'), 'actual_target_mismatch');
  assert(await summary.count() === 0, 'mismatch_has_no_old_summary');
  await page.getByRole('textbox', {name: '场景 ID', exact: true}).fill('synthetic-equipment-corridor');
  await button.click(); await summary.waitFor();
  await page.setViewportSize({width: 390, height: 844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile_no_horizontal_overflow');
  await panel.screenshot({path: 'output/playwright/delivery/mobile.png'});
  await page.setViewportSize({width: 1440, height: 1100});
  return {checks: results, test_only: true, authorized: false};
}
