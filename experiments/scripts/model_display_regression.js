// playwright-cli run-code --filename; run against the loopback L03 lab with
// a current production workbench build. No production sessions or data used.
globalThis.cospaceDisplayRegression = async page => {
  const origin = new URL(page.url()).origin;
  if (!/^http:\/\/127\.0\.0\.1:879[4-6]$/.test(origin)) throw new Error('Loopback lab required');
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const fixture = await (await page.request.get(origin + '/loading-lab/fixture')).json();
  const described = await (await page.request.get(origin + '/candidates/build-display-probe/api/display')).json();
  const agentPoints = fixture.anchors;
  const body = 'window.PREVIEW_VIEWS=' + JSON.stringify({agent_points: agentPoints}) + ';';
  const digest = await page.evaluate(async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))), n => n.toString(16).padStart(2, '0')).join(''), body);
  const model = {...described.model, space_id: 'space-display-regression',
    agent_view: {...described.model.agent_view, surface_cells: agentPoints.length},
    members: {...described.model.members, 'views.js': {bytes: new TextEncoder().encode(body).length, sha256: digest}}};
  const url = origin + '/space?screen=space&preview=1&space=' + model.space_id + '&job=' + model.id;
  let requests = 0, fail = false, release;
  let pending = new Promise(resolve => { release = resolve; });
  await page.route('**/api/auth/config', route => route.fulfill({json: {enabled: false, mode: 'engineering_preview'}}));
  await page.route('**/api/spaces', route => route.fulfill({json: {spaces: [{id: model.space_id, name: '合成园区 · 显示回归', publications: []}]}}));
  await page.route('**/candidates/build-display-probe/api/display', route => route.fulfill({json: {model, display: described.display}}));
  await page.route('**/candidates/build-display-probe/views.js', async route => {
    requests++;
    await pending;
    await route.fulfill({status: fail ? 502 : 200, contentType: 'text/javascript', body: fail ? 'synthetic fault' : body});
  });
  const host = page.locator('[data-provider="potree/1.8.2"]');
  const ready = () => page.waitForFunction(() => Number(document.querySelector('[data-provider]')?.dataset.displayPoints) > 0);
  const get = () => host.evaluate(element => ({...element.dataset}));
  const results = [];
  try {
    await page.setViewportSize({width: 1575, height: 883});
    await page.goto(url);
    await ready();
    await page.waitForFunction(() => Number(document.querySelector('[data-provider]')?.dataset.viewReadyMs) > 0);
    const initial = await get();
    check(initial.pointSizeCss === '2.2' && initial.pointSizeMode === 'fixed', 'Point size regressed');
    check(model.construction.model_points === fixture.display.point_count, 'Source point count changed');
    await page.screenshot({path: 'output/playwright/display-workbench-fixed.png'});
    // Hold the verified computation response to simulate a genuinely slow
    // request. The actual RealSpace switcher must keep rendering the cloud.
    await page.getByRole('button', {name: '切换到计算表达', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('[data-provider]')?.dataset.viewPending === 'true');
    for (let i = 0; i < 5; i++) {
      const value = await get();
      check(value.renderedView === 'human' && Number(value.displayPoints) > 0, 'Computation wait blanked the visual view');
      await page.waitForTimeout(200);
    }
    check(requests === 1, 'Computation was not prefetched exactly once');
    await page.screenshot({path: 'output/playwright/display-workbench-pending.png'});
    await page.getByRole('switch', {name: '显示真实几何', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('[data-provider]')?.dataset.displayPoints === '0');
    await page.getByRole('switch', {name: '显示真实几何', exact: true}).click();
    await ready();
    await page.getByRole('button', {name: '切换到视觉表达', exact: true}).click();
    await page.getByRole('button', {name: '切换到计算表达', exact: true}).click();
    check(requests === 1, 'Rapid toggles restarted the same request');
    release();
    await page.waitForFunction(() => document.querySelector('[data-provider]')?.dataset.renderedView === 'agent');
    check(Number((await get()).displayPoints) === agentPoints.length, 'Wrong computation point count');
    results.push({case: 'slow first load / prefetch / rapid toggles', passed: true});
    const switchStarted = Date.now();
    await page.getByRole('button', {name: '切换到视觉表达', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('[data-provider]')?.dataset.renderedView === 'human');
    await ready();
    await page.getByRole('button', {name: '切换到计算表达', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('[data-provider]')?.dataset.renderedView === 'agent');
    check(requests === 1, 'Warm switch downloaded computation again');
    results.push({case: 'warm round trip retains buffers', passed: true, roundTripMs: Date.now() - switchStarted});
    // A failed background read must leave a usable visual view and a next
    // explicit switch must retry, instead of waiting forever on a failed load.
    fail = true;
    await page.reload();
    await page.getByRole('alert').filter({hasText: '计算表达读取失败'}).waitFor();
    await ready();
    check((await get()).renderedView === 'human', 'Failure hid the visual view');
    fail = false;
    await page.getByRole('button', {name: '切换到计算表达', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('[data-provider]')?.dataset.renderedView === 'agent');
    check(requests === 3, 'Explicit retry did not recover computation');
    results.push({case: 'failed prefetch and explicit retry', passed: true});
    model.agent_view.surface_cells = 0;
    await page.reload();
    await ready();
    await page.getByRole('button', {name: '切换到计算表达', exact: true}).click();
    await page.getByRole('status').filter({hasText: '计算表达暂无表面单元'}).waitFor();
    check(requests === 3, 'Empty computation caused an unnecessary read');
    results.push({case: 'explicitly empty computation / geometry toggle', passed: true});
    return {results, originalPoints: fixture.display.point_count, initiallyRenderedPoints: Number(initial.displayPoints), initial};
  } finally {
    release();
    await page.unroute('**/api/auth/config');
    await page.unroute('**/api/spaces');
    await page.unroute('**/candidates/build-display-probe/api/display');
    await page.unroute('**/candidates/build-display-probe/views.js');
  }
}
