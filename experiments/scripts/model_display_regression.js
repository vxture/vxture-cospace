// Playwright CLI, real workbench on the synthetic loopback lab prepared with --dual.
globalThis.cospaceDisplayRegression = async page => {
  const origin = new URL(page.url()).origin;
  if (!/^http:\/\/127\.0\.0\.1:879[4-6]$/.test(origin)) throw new Error('Loopback lab required');
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const fixture = await (await page.request.get(origin + '/loading-lab/fixture')).json();
  const described = await (await page.request.get(origin + '/candidates/build-display-probe/api/display')).json();
  const model = {...described.model, space_id: 'space-display-regression', semantic_annotation: {object_count: 1}};
  const agent = described.agent_display;
  check(agent?.state === 'ready' && agent.point_count > 100000, 'Prepare a large dual fixture');
  const space = {id: model.space_id, name: '合成园区 · 双表达回归', publications: []};
  const url = origin + '/space?screen=space&preview=1&space=' + model.space_id + '&job=' + model.id;
  const descriptor = '**/candidates/build-display-probe/api/display';
  const objects = '**/candidates/build-display-probe/api/objects';
  const agentOctree = '**/display/' + agent.id + '/octree.bin';
  const usedAgentRanges = new Map();
  let release, fail = 0, failed = 0, sourceReads = 0, changeToEmpty = false;
  const hold = new Promise(resolve => { release = resolve; });
  const evidence = [];
  await page.addInitScript(() => {
    window.__dualFrames = [];
    addEventListener('message', event => {
      if (event.origin === location.origin && event.data?.channel === 'cospace.pointcloud/1' && event.data.type === 'frame') {
        const {view, pending, points, diagnostics} = event.data;
        window.__dualFrames.push({view, pending, points, camera: diagnostics.cameraSignature, time: performance.now()});
      }
    });
  });
  await page.route('**/api/auth/config', route => route.fulfill({json: {enabled: false, mode: 'engineering_preview'}}));
  await page.route('**/api/spaces', route => route.fulfill({json: {spaces: [space]}}));
  const source = model.members['spatial.npz'].sha256;
  await page.route(objects, route => route.fulfill({json: {model_id: model.id, source_model_sha256: source, frame_id: model.frame_id,
    objects: [{object_id:'far-edge', anchor_m: model.bounds_m[1].map(n => n - 1), type_id: 'synthetic-corner',
      properties: {name: '园区边缘作业点'}, evidence: {sha256: source}}]}}));
  await page.route(descriptor, route => route.fulfill({json: changeToEmpty ? {
    ...described, model: {...model, agent_view: {...model.agent_view, surface_cells: 0}},
    agent_display: {...agent, state: 'empty', point_count: 0, entry: null},
  } : {...described, model}}));
  const oldSource = '**/candidates/build-display-probe/{views.js,human.ply,agent.npz}';
  await page.route(oldSource, route => { sourceReads++; return route.abort(); });
  await page.route(agentOctree, async route => {
    const range = route.request().headers().range;
    usedAgentRanges.set(range, (usedAgentRanges.get(range) || 0) + 1);
    await hold;
    if (fail) { failed++; await route.fulfill({status: fail, body: 'synthetic local fault'}); }
    else await route.continue();
  });
  const canvas = '[data-provider="potree/1.8.2"]';
  const get = () => page.locator(canvas).evaluate(element => ({...element.dataset}));
  const rendered = (view, minPoints = 1) => page.waitForFunction(({canvas, view, minPoints}) => {
    const d = document.querySelector(canvas)?.dataset;
    return d?.renderedView === view && Number(d.displayPoints) >= minPoints;
  }, {canvas, view, minPoints}, {timeout: 25000});
  const toAgent = () => page.getByRole('button', {name: '切换到计算表达', exact: true}).click();
  const toHuman = () => page.getByRole('button', {name: '切换到视觉表达', exact: true}).click();
  const ready = () => page.waitForFunction(canvas => Number(document.querySelector(canvas)?.dataset.viewReadyMs) > 0, canvas, {timeout: 25000});
  try {
    await page.setViewportSize({width: 1575, height: 883});
    await page.goto(url);
    await rendered('human');
    await ready();
    const initial = await get();
    check(initial.pointSizeCss === '2.2' && initial.pointSizeMode === 'fixed', 'Fixed visual points regressed');
    check(model.construction.model_points === fixture.display.point_count, 'Source visual count changed');
    const waitStart = Date.now();
    while (!usedAgentRanges.size && Date.now() - waitStart < 8000) await page.waitForTimeout(50);
    check(usedAgentRanges.size === 1 && !usedAgentRanges.has(undefined), 'Computation root was not requested in the background as a bounded range');
    check(!await page.getByText(/正在准备计算表达|正在读取计算表达/).count(), 'Background loading leaked into the UI');
    await toAgent();
    await page.waitForFunction(canvas => document.querySelector(canvas)?.dataset.viewPending === 'true', canvas);
    await toHuman();
    await toAgent();
    await page.waitForTimeout(350);
    const pending = await get();
    check(pending.renderedView === 'human' && Number(pending.displayPoints) > 0, 'Waiting for computation blanked the visual view');
    check([...usedAgentRanges.values()].reduce((a, b) => a + b, 0) === 1, 'Rapid toggles restarted an outstanding range');
    await toHuman();
    release();
    await page.waitForFunction(canvas => Number(document.querySelector(canvas)?.dataset.agentRanges) >= 5, canvas, {timeout: 25000});
    const overview = await get();
    check(overview.renderedView === 'human' && Number(overview.agentPreparedPoints) > 0, 'Background did not refine beyond the overview');
    check(Number(overview.agentOctreeBytes) < Number(overview.agentOctreeTotal), 'Background downloaded the complete computation octree');
    evidence.push({case: 'slow background and early rapid switch', overview});

    const center = await page.locator(canvas).boundingBox();
    await page.mouse.move(center.x + center.width / 2, center.y + center.height / 2);
    for (let i = 0; i < 12; i++) { await page.mouse.wheel(0, -460); await page.waitForTimeout(100); }
    await page.waitForFunction(({canvas, ranges, camera}) => {
      const d = document.querySelector(canvas)?.dataset;
      return d?.renderedView === 'human' && d.cameraSignature !== camera && Number(d.agentRanges) > ranges;
    }, {canvas, ranges: Number(overview.agentRanges), camera: overview.cameraSignature}, {timeout: 25000});
    await ready();
    const warm = await get();
    check(Number(warm.agentPreparedPoints) > 0, 'Camera movement lost prepared computation geometry');
    await page.screenshot({path: 'output/playwright/l04-visual.png'});
    const switchedAt = await page.evaluate(() => performance.now());
    await toAgent();
    await rendered('agent');
    const current = await get();
    const frames = await page.evaluate(since => window.__dualFrames.filter(frame => frame.time >= since), switchedAt);
    check(current.pointSizeCss === '3' && current.cameraSignature === warm.cameraSignature, 'Switch changed the camera or calculation point style');
    check(frames.length > 0 && frames.every(frame => frame.points > 0), 'Warm switch blanked at least one reported frame');
    await page.screenshot({path: 'output/playwright/l04-calculation.png'});
    await toHuman();
    await rendered('human');
    await toAgent();
    await rendered('agent');
    check([...usedAgentRanges.values()][0] === 1, 'Warm switches fetched the same root again');
    evidence.push({case: 'background follows zoom; same camera on warm switches', warm, switchMs: frames.find(frame => frame.view === 'agent').time - switchedAt});

    const reverseStart = await get();
    await page.getByRole('button', {name: '展开或收起对象列表', exact: true}).click();
    await page.getByRole('button', {name: '园区边缘作业点', exact: true}).click();
    await page.waitForFunction(({canvas, ranges, camera}) => {
      const d = document.querySelector(canvas)?.dataset;
      return d?.renderedView === 'agent' && d.cameraSignature !== camera && Number(d.humanRanges) > ranges;
    }, {canvas, ranges: Number(reverseStart.humanRanges), camera: reverseStart.cameraSignature}, {timeout: 20000});
    const reverseEnd = await get();
    await toHuman();
    await rendered('human');
    evidence.push({case: 'visual background refines when calculation is foreground', before: Number(reverseStart.humanRanges), after: Number(reverseEnd.humanRanges)});

    fail = 502;
    await page.reload();
    await rendered('human');
    const faultStart = Date.now();
    while (!failed && Date.now() - faultStart < 8000) await page.waitForTimeout(50);
    check(failed > 0 && (await get()).renderedView === 'human', 'No background transport fault was exercised');
    check(!await page.getByText('部分模型数据暂不可读，请重试。', {exact: true}).count(), 'Inactive retry leaked into the UI');
    fail = 0;
    await toAgent();
    await rendered('agent');
    await page.getByRole('switch', {name: '显示真实几何', exact: true}).click();
    await page.waitForFunction(canvas => document.querySelector(canvas)?.dataset.displayPoints === '0', canvas);
    await page.getByRole('switch', {name: '显示真实几何', exact: true}).click();
    await rendered('agent');
    evidence.push({case: 'silent background failure; explicit retry and geometry toggle'});

    changeToEmpty = true;
    await page.reload();
    await rendered('human');
    const beforeEmpty = [...usedAgentRanges.values()].reduce((a, b) => a + b, 0);
    await toAgent();
    await rendered('agent', 0);
    await page.getByRole('status').filter({hasText: '计算表达暂无表面单元'}).waitFor();
    check([...usedAgentRanges.values()].reduce((a, b) => a + b, 0) === beforeEmpty, 'Empty computation attempted a file read');
    check(sourceReads === 0, 'Main preview requested an entire source artifact');
    evidence.push({case: 'explicit empty computation; no full source requests'});

    changeToEmpty = false;
    fail = 403;
    await page.reload();
    await page.getByRole('alert').filter({hasText: '当前模型的访问或版本状态已变化'}).first().waitFor();
    check(!await page.frameLocator('iframe[title="空间模型渐进画布"]').locator('canvas').count(), 'Access revocation during secondary loading left an authorized frame visible');
    evidence.push({case: 'background authorization failure clears both views'});
    return {evidence, originalVisualPoints: fixture.display.point_count, originalComputationUnits: agent.point_count};
  } finally {
    release();
    for (const path of ['**/api/auth/config', '**/api/spaces', descriptor, objects, oldSource, agentOctree]) await page.unroute(path);
  }
};
