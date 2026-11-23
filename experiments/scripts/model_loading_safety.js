// playwright-cli run-code --filename; only the local synthetic lab is allowed.
async page => {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:8794') throw Error('Loopback lab required');
  const url = 'http://127.0.0.1:8794/loading-lab?task=true&strategy=combined';
  const ready = () => page.waitForFunction(() => JSON.parse(document.getElementById('diagnostics').textContent || '{}').viewReadyMs > 0);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const results = [];
  await page.goto(url);
  await ready();
  let frame = page.frames()[1];
  // Capture this lab's native viewer through its public setter, without changing
  // production code or taking over native visibility/loading queues.
  await frame.evaluate(() => {
    const original = Potree.Viewer.prototype.setPointBudget;
    Potree.Viewer.prototype.setPointBudget = function(value) {
      window.__labViewer = this;
      return original.call(this, value);
    };
  });
  await page.getByRole('button', {name: '全图', exact: true}).click();
  await frame.waitForFunction(() => !!window.__labViewer);
  const states = await frame.evaluate(() => {
    const v = window.__labViewer;
    Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
    dispatchEvent(new Event('visibilitychange'));
    const hidden = v.getFreeze();
    delete document.hidden;
    dispatchEvent(new Event('visibilitychange'));
    return {hidden, resumed: !v.getFreeze()};
  });
  check(states.hidden && states.resumed, 'Hidden native selection did not pause/resume');
  await page.evaluate(() => post('settings', {view: 'agent', geometry: true}));
  await frame.waitForFunction(() => window.__labViewer.getFreeze());
  await page.evaluate(() => post('retry'));
  check(await frame.evaluate(() => window.__labViewer.getFreeze()), 'Retry bypassed nonhuman pause');
  await page.evaluate(() => post('settings', {view: 'human', geometry: false}));
  await frame.waitForFunction(() => !window.__labViewer.scene.pointclouds[0].visible);
  await page.evaluate(() => post('settings', {view: 'human', geometry: true}));
  await frame.waitForFunction(() => !window.__labViewer.getFreeze() && window.__labViewer.scene.pointclouds[0].visible);
  await ready();
  results.push({case: 'hidden/agent/geometry/retry', passed: true, simulatedVisibility: true});

  await frame.evaluate(async () => {
    const {LoadingPolicy} = await import('/assets/pointcloud-runtime/loading-policy.js');
    window.__originalBudget = LoadingPolicy.prototype.budget;
    LoadingPolicy.prototype.budget = () => { throw Error('Synthetic optional-policy fault'); };
  });
  await page.waitForFunction(() => JSON.parse(document.getElementById('diagnostics').textContent || '{}').strategyFallback === true);
  const fallback = JSON.parse(await page.locator('#diagnostics').textContent());
  check(fallback.pointBudget === 500000 && fallback.nodePixels === 30 && fallback.nativeLoadSlots === 4, 'Fallback changed mature quality');
  await frame.evaluate(async () => {
    const {LoadingPolicy} = await import('/assets/pointcloud-runtime/loading-policy.js');
    LoadingPolicy.prototype.budget = window.__originalBudget;
    const until = performance.now() + 1100;
    while (performance.now() < until) {} // A real foreground stall must remain visible in telemetry.
  });
  await page.waitForFunction(() => JSON.parse(document.getElementById('diagnostics').textContent || '{}').peakFrameMs >= 1000);
  results.push({case: 'optional strategy exception and long-frame telemetry', passed: true});

  for (const status of [502, 200, 401, 403, 409]) {
    await page.goto(url);
    await ready();
    frame = page.frames()[1];
    await page.evaluate(() => {
      window.__labErrors = [];
      addEventListener('message', e => {
        if (e.source === frame.contentWindow && e.data?.channel === channel && e.data.type === 'error') window.__labErrors.push(e.data);
      });
    });
    let blocked = 0;
    const intercept = route => { blocked++; return route.fulfill({status, body: 'synthetic local fault'}); };
    await page.route('**/display/**/octree.bin', intercept);
    try {
      await page.getByRole('button', {name: '全图', exact: true}).click();
      await page.waitForFunction(() => window.__labErrors.length > 0);
      const access = await page.evaluate(() => window.__labErrors.some(e => e.access));
      check(access === [401, 403, 409].includes(status), 'Access failure misclassified');
      check((await frame.locator('canvas').count() === 0) === access, 'Fault incorrectly cleared or retained canvas');
      results.push({case: 'range status ' + status, passed: true, accessCleared: access, intercepted: blocked});
    } finally {
      await page.unroute('**/display/**/octree.bin', intercept);
    }
    if (![401, 403, 409].includes(status)) {
      await page.evaluate(() => post('retry'));
      await ready();
      check(JSON.parse(await page.locator('#diagnostics').textContent()).points > 0, 'Partial failure did not recover');
    }
  }
  return results;
}
