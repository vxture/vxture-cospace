// Playwright CLI run-code; local server must expose a clean 0.2 saved report.
async (page) => {
  await page.goto('http://127.0.0.1:8771/workbench/');
  const checks = [];
  const assert = (value, name) => {if (!value) throw new Error(name); checks.push(name);};
  const panel = page.locator('#delivery');
  const button = panel.getByRole('button', {name: '读取 / 刷新交付报告'});
  await button.click();
  const generation = panel.getByTestId('delivery-generation');
  await generation.waitFor();
  const url = '/scenes/synthetic-equipment-corridor/releases/release-spatial-sample-001/delivery';
  const actual = await (await page.request.get(new URL(url, page.url()).href)).json();
  const id = actual.report.generation.report_id;
  assert((await generation.innerText()).includes(id), 'actual_report_batch_displayed');
  assert((await generation.innerText()).includes('观察开始：') &&
    (await generation.innerText()).includes('观察结束：'), 'observation_interval_displayed');
  assert((await generation.innerText()).includes('单调计时耗时：'), 'monotonic_duration_displayed');
  const fullTime = /\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2}\.\d{3}/;
  assert(fullTime.test(await generation.innerText()), 'full_calendar_datetime_displayed');
  assert(fullTime.test(await panel.getByText(/^本次读取：/).innerText()), 'read_time_has_full_calendar_datetime');
  assert(await panel.getByTestId('delivery-legacy').count() === 0, 'new_report_not_labelled_legacy');
  await button.click(); await generation.waitFor();
  assert((await generation.innerText()).includes(id), 'reread_keeps_same_batch');
  await panel.getByText('报告生成与来源上下文', {exact: true}).click();
  assert((await panel.innerText()).includes(actual.report.generation.sources.files.locator_sha256), 'file_locator_fingerprint_displayed');
  assert((await panel.innerText()).includes(actual.report.generation.sources.journal.control.store_id), 'journal_store_identity_displayed');
  assert((await panel.innerText()).includes('摘要未签名，不提供来源认证'), 'checksum_does_not_claim_authentication');
  await panel.screenshot({path: 'output/playwright/delivery-context/context.png'});
  await page.setViewportSize({width: 390, height: 844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile_context_no_horizontal_overflow');
  await panel.screenshot({path: 'output/playwright/delivery-context/mobile.png'});
  await page.setViewportSize({width: 1440, height: 1100});
  const backward = JSON.parse(JSON.stringify(actual));
  Object.assign(backward.report.generation.interval, {started_at: '2026-10-27T00:00:02.000000Z',
    finished_at: '2026-10-27T00:00:01.000000Z', elapsed_ms: 100, wall_end_before_start: true});
  await page.route('**/delivery', route => route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(backward)}));
  await button.click(); await generation.waitFor();
  assert((await generation.getByRole('alert').innerText()).includes('结束时间早于开始时间'), 'mocked_backward_clock_explicit_warning');
  assert((await generation.innerText()).includes('100毫秒'), 'backward_clock_preserves_monotonic_duration');
  await page.unroute('**/delivery');
  await button.click(); await generation.waitFor();
  return {checks, injected: ['backward wall clock response'], authorized: false, test_only: true};
}
