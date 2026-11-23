// Run through playwright-cli run-code --filename against the loopback lab.
// One cold condition; an external runner randomizes/repeats conditions and saves results.
globalThis.cospaceLoadingProbe = async page => {
  const url = new URL(page.url());
  if (url.origin !== 'http://127.0.0.1:8794' || url.pathname !== '/loading-lab') throw new Error('Synthetic loopback lab required');
  await page.setViewportSize({width: 1920, height: 1080});
  const cdp = await page.context().newCDPSession(page);
  const read = () => page.locator('#diagnostics').textContent().then(JSON.parse);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', {cacheDisabled: true});
  await cdp.send('Network.emulateNetworkConditions', {offline: false, latency: 100, downloadThroughput: 625000, uploadThroughput: 1250000});
  try {
    await page.reload();
    await page.waitForFunction(() => JSON.parse(document.getElementById('diagnostics').textContent || '{}').firstMs > 0, {}, {timeout: 45000});
    await page.getByRole('button', {name: '核验原始点', exact: true}).click();
    await page.waitForFunction(() => {
      const v = JSON.parse(document.getElementById('diagnostics').textContent || '{}');
      return v.viewReadyMs > 0 && v.exactMs > 0;
    }, {}, {timeout: 45000});
    const initial = await read();
    if (!initial.exactValid || !initial.accounting_complete || initial.strategyFallback) throw new Error('Initial correctness gate failed');
    await page.getByRole('button', {name: '快速切换作业区域', exact: true}).click();
    await page.waitForFunction(() => {
      const v = JSON.parse(document.getElementById('diagnostics').textContent || '{}');
      return v.pathEndedMs > 0 && v.viewReadyMs >= v.pathEndedMs && v.nowMs >= v.pathEndedMs + 10000;
    }, {}, {timeout: 60000});
    const final = await read();
    const metrics = {modelMs: initial.firstMs, initialViewMs: initial.viewReadyMs,
      exactMs: initial.exactMs, movedViewMs: final.viewReadyMs - final.pathEndedMs,
      unusedBytes: final.unused_bytes, transferBytes: final.octree_bytes,
      frameP95Ms: final.peakFrameP95Ms, maxFrameMs: final.peakFrameMs,
      cachedPoints: final.cachedPoints};
    const source = await page.evaluate(() => ({displayId: fixture.display.id,
      sourceModelSha256: fixture.display.source_model_sha256, sourceManifestSha256: fixture.display.source_manifest_sha256,
      fixtureManifestSha256: fixture.fixture_manifest_sha256, pointCount: fixture.display.point_count}));
    return {strategy: url.searchParams.get('strategy') || 'baseline', sample: initial.sample, source,
      network: '5Mbps/100ms', viewport: '1920x1080/DPR1', metrics, initial, final};
  } finally {
    await cdp.send('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
    await cdp.send('Network.setCacheDisabled', {cacheDisabled: false});
    await cdp.detach();
  }
}
