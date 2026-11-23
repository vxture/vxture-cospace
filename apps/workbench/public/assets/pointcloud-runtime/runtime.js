/* Potree runs in its own realm. No platform Three objects or authentication state cross this bridge. */
import {LoadingPolicy, TransferLedger, BASELINE, percentile} from './loading-policy.js';
(() => {
  'use strict';
  const channel = 'cospace.pointcloud/1';
  let session = '', viewer, config, objects = [], firstFrame = false, disposed = false;
  let lastReport = 0, requests = 0, transferred = 0, fatal = false, paused = false, geometry = true, picking = false;
  let dual = false, requested = 'human', rendered = 'human', lastSecondary = 0;
  const layer = () => ({descriptor: null, cloud: null, opening: false, nodes: new Set(), retryAt: 0, error: '', requests: 0, bytes: 0, octreeBytes: 0, octreeTotal: 0, loading: 0});
  const layers = {human: layer(), agent: layer()};
  const controllers = new Set();
  const ledger = new TransferLedger(), frameTimes = [];
  let policy = new LoadingPolicy(), appliedBudget = '', lastFrame = 0, cameraKey = '', cameraChangedAt = 0;
  let settledSince = 0, viewReadyAt = 0, visibleKey = '', frameP95 = 0, policyFallback = false;
  const send = (type, values = {}) => parent.postMessage({channel, session, type, ...values}, location.origin);
  function fail(message, access = false) {
    if (!access && paused) return;
    if (access) {
      fatal = true;
      for (const c of controllers) c.abort();
      viewer?.renderer.setAnimationLoop(null);
      viewer?.renderer.clear();
      document.getElementById('canvas').replaceChildren();
    } else {
      paused = true;
      viewer?.setFreeze(true);
    }
    send('error', {message, access});
  }
  function failLayer(key, message) {
    if (!dual) { fail(message); return; }
    const item = layers[key];
    item.retryAt = performance.now() + 3500;
    item.error = message;
  }
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!config || !url.pathname.includes('/display/')) return nativeFetch(input, init);
    const key = Object.keys(layers).find(name => layers[name].descriptor?.entry?.replace(/metadata\.json$/, '') === url.pathname.replace(/[^/]+$/, ''));
    if (!key || url.origin !== location.origin || url.search || !/\/(metadata\.json|hierarchy\.bin|octree\.bin)$/.test(url.pathname) || fatal || paused || disposed) {
      throw Error('display_context_changed');
    }
    const item = layers[key];
    const controller = new AbortController();
    const started = performance.now();
    controllers.add(controller);
    try {
      const callerSignal = init.signal || (input instanceof Request ? input.signal : null);
      const signal = callerSignal ? AbortSignal.any([controller.signal, callerSignal]) : controller.signal;
      const response = await nativeFetch(input, {...init, signal, credentials: 'same-origin', cache: 'no-store',
        priority: key === requested ? 'high' : 'low'});
      const ttfb = performance.now() - started;
      if ([401, 403, 409].includes(response.status)) {
        fail('当前模型的访问或版本状态已变化，请重新打开。', true);
        throw Error('display_access_changed');
      }
      const range = new Headers(init.headers || (input instanceof Request ? input.headers : undefined)).get('range');
      const requested = /^bytes=(\d+)-(\d+)$/.exec(range || '');
      const returned = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('content-range') || '');
      const validRange = requested && returned && response.status === 206 &&
        Number(returned[1]) === Number(requested[1]) && Number(returned[2]) === Number(requested[2]) &&
        Number(returned[2]) < Number(returned[3]) && Number(returned[2]) - Number(returned[1]) < 16 * 1024 * 1024;
      if (!response.ok || (range ? !validRange : response.status !== 200 || !url.pathname.endsWith('/metadata.json'))) {
        await response.body?.cancel();
        throw Error('display_read_failed');
      }
      // Keep cancellation attached through the body, not just until headers arrive.
      const expected = range ? Number(returned[2]) - Number(returned[1]) + 1 : Number(response.headers.get('content-length'));
      if (!Number.isSafeInteger(expected) || expected <= 0 || expected > (range ? 16 * 1024 * 1024 : 50 * 1024)) {
        await response.body?.cancel(); throw Error('display_response_budget');
      }
      const raw = await response.arrayBuffer();
      if (signal.aborted || fatal || disposed) throw new DOMException('Aborted', 'AbortError');
      if (raw.byteLength !== expected) throw Error('display_response_truncated');
      requests++;
      transferred += raw.byteLength;
      item.requests++; item.bytes += raw.byteLength;
      if (item.retryAt <= performance.now()) item.error = '';
      if (key === rendered) policy.observeNetwork(raw.byteLength, performance.now() - started, ttfb);
      if (url.pathname.endsWith('/octree.bin')) {
        if (key === 'human') ledger.received(range, raw.byteLength);
        item.octreeBytes += raw.byteLength;
        item.octreeTotal = Number(returned[3]);
      }
      return new Response(raw, {status: response.status, statusText: response.statusText, headers: response.headers});
    } catch (error) {
      if (error.name !== 'AbortError' && !fatal && !disposed) failLayer(key, '部分模型数据暂不可读，请重试。');
      throw error;
    } finally {
      controllers.delete(controller);
    }
  };
  function local(point) {
    const result = point.map((n, i) => n - config.origin_m[i]);
    return config.model_to_display.map(row => row.reduce((n, v, i) => n + v * result[i], 0));
  }
  function apply() {
    for (const [key, item] of Object.entries(layers)) if (item.cloud) item.cloud.visible = geometry && rendered === key;
  }
  const nodes = item => item.cloud?.visibleNodes || [];
  const pointCount = item => nodes(item).reduce((sum, node) => sum + (node.sceneNode?.geometry?.attributes.position.count || 0), 0);
  const other = key => key === 'human' ? 'agent' : 'human';
  const available = item => item.descriptor?.state === 'ready' && item.retryAt <= performance.now();
  function agentDescriptor(value) {
    if (!dual || layers.agent.cloud || layers.agent.opening) return;
    if (value && (value.id === config.id || value.view !== 'agent' || value.source_manifest_sha256 !== config.source_manifest_sha256 ||
      value.source_model_sha256 !== config.source_model_sha256 || (value.state === 'ready' && (!validEntry(value) ||
        value.entry.split('/display/')[0] !== config.entry.split('/display/')[0] ||
        JSON.stringify(value.origin_m) !== JSON.stringify(config.origin_m) || JSON.stringify(value.model_to_display) !== JSON.stringify(config.model_to_display))))) return;
    layers.agent.descriptor = value || null;
  }
  function validEntry(value) {
    return value && typeof value.id === 'string' && typeof value.entry === 'string' &&
      /^\/(candidates\/build-[A-Za-z0-9-]+|publications\/preview-[a-f0-9]{16})\/display\/[a-f0-9]{64}\/metadata\.json$/.test(value.entry) &&
      value.entry.endsWith(`/display/${value.id}/metadata.json`);
  }
  function updatePolicy(now) {
    if (!viewer || fatal || disposed) return;
    const camera = viewer.scene.getActiveCamera();
    const next = [...camera.position.toArray(), ...camera.quaternion.toArray(), camera.aspect].map(n => n.toFixed(6)).join('|');
    if (next !== cameraKey) { cameraKey = next; cameraChangedAt = now; settledSince = 0; viewReadyAt = 0; }
    try {
      const budget = policy.budget({moving: now - cameraChangedAt < 350, hidden: document.hidden,
        browsing: geometry, frameMs: frameP95, decoding: Math.max(0, Potree.numNodesLoading - controllers.size)});
      const key = JSON.stringify(budget);
      if (key !== appliedBudget) {
        appliedBudget = key;
        viewer.setPointBudget(budget.points);
        viewer.setMinNodeSize(budget.nodePixels);
        Potree.maxNodesLoading = budget.loads;
        viewer.setFreeze(paused || budget.freeze);
      }
    } catch {
      // A failed optional strategy must not weaken authorization or change data.
      policy.disable(); policyFallback = true; appliedBudget = '';
      viewer.setPointBudget(BASELINE.points); viewer.setMinNodeSize(BASELINE.nodePixels);
      Potree.maxNodesLoading = BASELINE.loads; viewer.setFreeze(paused);
    }
  }
  function focusTo(point) {
    if (!Array.isArray(point) || point.length !== 3 || !point.every(Number.isFinite)) return;
    const view = viewer.scene.view, next = new THREE.Vector3(...local(point));
    const direction = view.getPivot().sub(view.position).normalize();
    const radius = Math.max(.5, Math.min(view.radius, 10));
    view.position.copy(next).addScaledVector(direction, -radius);
    view.lookAt(next); view.radius = radius;
  }
  function fit() {
    const visual = layers.human.cloud;
    if (!visual) return;
    // Both views share one camera; frame the same visual bounds every time.
    const bounds = new THREE.Object3D();
    bounds.boundingBox = viewer.getBoundingBox([visual]);
    viewer.zoomTo(bounds, 1.1, 0);
    viewer.controls.stop();
    // Native zoomTo uses a zero-duration tween, completed on the next update.
    // Complete it before accepting an explicit task focus, which it would overwrite.
    // This pinned tween version computes 0/0 when start and update share a tick.
    TWEEN.update(performance.now() + 1);
  }
  function installDualSelection() {
    const nativeUpdate = Potree.updatePointClouds;
    Potree.updatePointClouds = (_, camera, renderer) => {
      const primary = available(layers[requested]) ? requested : rendered;
      const secondary = other(primary), front = layers[primary], back = layers[secondary];
      const now = performance.now(), budget = Potree.pointBudget;
      const total = Potree.maxNodesLoading;
      const background = available(back) && total >= 2;
      const activeSlots = total - (background ? 1 : 0);
      const update = (item, limit, slots, pixels) => {
        if (!item.cloud) return null;
        if (item.retryAt > now) return null; // Keep already submitted geometry on a transient failure.
        item.loading = slots;
        item.cloud.visible = true;
        item.cloud.minimumNodePixelSize = pixels;
        Potree.pointBudget = limit;
        try { return nativeUpdate([item.cloud], camera, renderer); }
        finally { Potree.pointBudget = budget; apply(); }
      };
      const frontResult = update(front, budget, activeSlots, viewer.minNodeSize);
      let backResult = null;
      // The inactive view gets a reserved network/decode slot and follows the
      // same camera. Cap its traversal and cache footprint independently.
      if (background && now - lastSecondary >= (frameP95 > 33 ? 220 : 100)) {
        lastSecondary = now;
        const retaining = secondary === rendered;
        backResult = update(back, retaining ? budget : Math.min(180000, Math.floor(budget * .5)), 1,
          retaining ? viewer.minNodeSize : Math.max(viewer.minNodeSize, 38));
        if (back.cloud) prepareBuffer(back);
      }
      return (rendered === primary ? frontResult : backResult) || frontResult || backResult || {lowestSpacing: Infinity, visibleNodes: [], numVisiblePoints: 0};
    };
  }
  function prepareBuffer(item) {
    const native = viewer.pRenderer;
    // Prepare one native GPU buffer per traversal, without drawing a second view.
    const candidate = nodes(item).find(node => node.sceneNode?.geometry?.attributes.position.count && !native.buffers.has(node.sceneNode.geometry));
    if (candidate) {
      const target = candidate.sceneNode.geometry;
      native.buffers.set(target, native.createBuffer(target));
    }
  }
  function beforeRender() {
    if (!dual || !geometry || requested === rendered || fatal || disposed) return;
    const target = layers[requested];
    if (target.descriptor?.state !== 'empty') {
      if (!pointCount(target)) return;
      const native = viewer.pRenderer;
      if (!nodes(target).some(node => native.buffers.has(node.sceneNode?.geometry))) prepareBuffer(target);
    }
    rendered = requested;
    settledSince = 0; viewReadyAt = 0; visibleKey = '';
    apply();
  }
  function report() {
    if (!layers.human.cloud || disposed || fatal) return;
    const now = performance.now();
    if (lastFrame && !document.hidden) {
      frameTimes.push(now - lastFrame);
      if (frameTimes.length > 240) frameTimes.shift();
    }
    lastFrame = now;
    updatePolicy(now);
    if (dual && geometry && !document.hidden && !layers.agent.cloud && !layers.agent.opening && available(layers.agent) && Potree.numNodesLoading < Potree.maxNodesLoading) {
      layers.agent.opening = true;
      void openCloud('agent').catch(() => {
        if (!fatal && !disposed && !layers.agent.error) failLayer('agent', '计算表达暂不可读，请重试。');
      }).finally(() => { layers.agent.opening = false; });
    }
    // numVisiblePoints includes queued, undecoded nodes in upstream Potree.
    // Only loaded tree nodes submitted in this completed render pass count as geometry.
    const current = layers[rendered];
    const points = geometry ? pointCount(current) : 0;
    if (geometry && rendered === 'human') for (const node of nodes(current)) {
      const original = node.geometryNode;
      if (node.sceneNode?.geometry && original?.byteSize > 0n) ledger.rendered(`bytes=${original.byteOffset}-${original.byteOffset + original.byteSize - 1n}`);
    }
    if (!firstFrame && points > 0) {
      firstFrame = true;
      send('first-frame', {points, elapsed_ms: performance.now(), requests, transferred});
    }
    if (now - lastReport < 160) return;
    lastReport = now;
    frameP95 = percentile(frameTimes, .95);
    const signature = nodes(current).map(n => n.name).sort().join('|');
    // Identical stable quality for baseline and strategies. Reduced motion
    // quality or an empty frame can never be reported as ready.
    const budget = JSON.parse(appliedBudget || JSON.stringify(BASELINE));
    const activeLoads = dual ? [...current.nodes].filter(node => node.loading).length : Potree.numNodesLoading;
    if (now - cameraChangedAt >= 350 && points > 0 && geometry && !document.hidden && !paused &&
      activeLoads === 0 && !current.error && budget.points === BASELINE.points && budget.nodePixels === BASELINE.nodePixels) {
      if (signature !== visibleKey) { visibleKey = signature; settledSince = now; viewReadyAt = 0; }
      if (!settledSince) settledSince = now;
      if (!viewReadyAt && now - settledSince >= 500) viewReadyAt = now;
    } else { settledSince = 0; viewReadyAt = 0; }
    const camera = viewer.scene.getActiveCamera();
    const labels = objects.map(object => {
      const p = new THREE.Vector3(...local(object.anchor_m)).project(camera);
      return {id: object.object_id, x: (p.x + 1) / 2, y: (1 - p.y) / 2, visible: p.z >= -1 && p.z <= 1 && Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1};
    });
    const target = layers[requested], empty = target.descriptor?.state === 'empty';
    const unavailable = requested === 'agent' && (!target.descriptor || ['unavailable', 'failed'].includes(target.descriptor.state));
    const fault = target.error || (unavailable ? '计算表达暂不可用。' : '');
    send('frame', {points, view: rendered, pending: requested !== rendered, empty, fault,
      loading: activeLoads, requests, transferred, labels,
      cached_points: Potree.lru.numPoints,
      geometries: viewer.renderer.info.memory.geometries,
      diagnostics: {strategy: policy.strategy, strategyFallback: policyFallback, viewReadyMs: viewReadyAt, runtimeNowMs: now,
        viewSignature: signature, cameraSignature: cameraKey,
        frameP95Ms: frameP95, frameMaxMs: Math.max(0, ...frameTimes),
        pointBudget: budget.points, nodePixels: budget.nodePixels,
        nativeLoadSlots: Potree.maxNodesLoading, pointSizeCss: rendered === 'human' ? 2.2 : 3, pointSizeMode: 'fixed',
        humanRanges: layers.human.requests, agentRanges: layers.agent.requests, agentBytes: layers.agent.bytes,
        agentOctreeBytes: layers.agent.octreeBytes, agentOctreeTotal: layers.agent.octreeTotal,
        humanPreparedPoints: pointCount(layers.human), agentPreparedPoints: pointCount(layers.agent), ...ledger.snapshot()}});
  }
  async function openCloud(key) {
    const item = layers[key], descriptor = item.descriptor;
    const loaded = await Potree.OctreeLoader.load(new URL(descriptor.entry, location.origin).href);
    if (disposed || fatal) return;
    if (loaded.geometry.loader.metadata.points !== descriptor.point_count) throw Error('display_point_count');
    const cloud = new Potree.PointCloudOctree(loaded.geometry);
    const position = loaded.geometry.loader.metadata.attributes.find(a => a.name === 'position');
    const offset = loaded.geometry.offset;
    if (position) {
      // Camera framing uses tight bounds; the native octree's cubic bounds stay intact.
      cloud.boundingBox = loaded.geometry.boundingBox.clone();
      cloud.boundingBox.min.set(...position.min).sub(offset);
      cloud.boundingBox.max.set(...position.max).sub(offset);
      loaded.geometry.tightBoundingBox = cloud.boundingBox.clone();
    }
    cloud.material.activeAttributeName = 'rgba';
    cloud.material.pointSizeType = Potree.PointSizeType.FIXED;
    cloud.material.size = (key === 'human' ? 2.2 : 3) * viewer.renderer.getPixelRatio();
    cloud.material.minSize = cloud.material.size;
    cloud.material.uniforms.maxSize.value = cloud.material.size;
    cloud.material.shape = Potree.PointShape.CIRCLE;
    if (dual) {
      const loader = loaded.geometry.loader, load = loader.load.bind(loader);
      if (loaded.geometry.root.loading) item.nodes.add(loaded.geometry.root);
      loader.load = node => {
        for (const inflight of item.nodes) if (!inflight.loading) item.nodes.delete(inflight);
        if (!available(item) || document.hidden || item.nodes.size >= item.loading || node.loaded || node.loading) return;
        item.nodes.add(node);
        return load(node);
      };
    }
    item.cloud = cloud;
    cloud.visible = key === rendered && geometry;
    viewer.scene.addPointCloud(cloud);
    cloud.updateMatrixWorld(true);
  }
  async function start(value, initialFocus, otherView, useDual) {
    if (viewer || disposed) return;
    config = value;
    dual = useDual === true;
    policy = new LoadingPolicy(config.strategy);
    if (!validEntry(config)) {
      fail('模型显示入口无效。', true); return;
    }
    layers.human.descriptor = config;
    agentDescriptor(otherView);
    try {
      Potree.maxNodesLoading = 4;
      viewer = new Potree.Viewer(document.getElementById('canvas'), {noDragAndDrop: true});
      viewer.setEDLEnabled(false);
      viewer.setFOV(42);
      viewer.setPointBudget(500000);
      viewer.setMinNodeSize(30);
      viewer.setBackground('black');
      viewer.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
      viewer.renderer.domElement.setAttribute('aria-label', '真实空间渐进三维画布');
      viewer.renderer.domElement.addEventListener('dblclick', event => {
        const cloud = layers.human.cloud;
        if (!picking || !cloud || rendered !== 'human' || !geometry || paused || fatal || disposed) return;
        event.preventDefault(); event.stopImmediatePropagation();
        const rect = viewer.renderer.domElement.getBoundingClientRect();
        const hit = Potree.Utils.getMousePointCloudIntersection(new THREE.Vector2(event.clientX - rect.left, event.clientY - rect.top), viewer.scene.getActiveCamera(), viewer, [cloud]);
        if (!hit) return;
        const p = hit.location.toArray();
        // A displayed LOD hit supplies only a candidate region, never an original row ID.
        const point = config.origin_m.map((n, i) => n + config.model_to_display.reduce((sum, row, j) => sum + row[i] * p[j], 0));
        send('pick', {point});
      }, true);
      if (dual) {
        installDualSelection();
        viewer.addEventListener('render.pass.begin', beforeRender);
      }
      viewer.addEventListener('render.pass.end', report);
      // 1.8.2's convenience loadPointCloud invokes OctreeLoader twice for metadata.json.
      // Use its exported native loader directly, retaining the upstream LOD/decoder.
      await openCloud('human');
      if (disposed || fatal) return;
      fit();
      if (policy.task) focusTo(initialFocus);
      apply();
      send('initialized');
    } catch {
      if (!fatal && !disposed) fail('三维画布初始化失败，请核对浏览器图形能力或重试。');
    }
  }
  addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== parent || event.data?.channel !== channel) return;
    const value = event.data;
    if (value.type === 'init' && !session && typeof value.session === 'string') {
      session = value.session;
      void start(value.config, value.focus, value.agent, value.dual);
      return;
    }
    if (value.session !== session || !viewer || disposed || fatal) return;
    if (value.type === 'retry') {
      paused = false;
      layers[requested].retryAt = 0;
      layers[requested].error = '';
      appliedBudget = ''; updatePolicy(performance.now());
    }
    if (value.type === 'reset') fit();
    if (value.type === 'focus' && Array.isArray(value.point) && value.point.length === 3 && value.point.every(Number.isFinite)) {
      focusTo(value.point);
    }
    if (value.type === 'settings') {
      geometry = value.geometry;
      const next = dual && value.view === 'agent' ? 'agent' : 'human';
      if (requested !== next) {
        requested = next;
        layers[next].retryAt = 0;
        layers[next].error = '';
      }
      objects = Array.isArray(value.objects) ? value.objects : [];
      picking = value.picking === true;
      if (value.engineering) viewer.setBackground('gradient');
      apply();
      updatePolicy(performance.now());
    }
    if (value.type === 'agent-descriptor') agentDescriptor(value.config);
  });
  addEventListener('visibilitychange', () => { lastFrame = 0; updatePolicy(performance.now()); });
  addEventListener('pagehide', () => {
    disposed = true;
    for (const controller of controllers) controller.abort();
    viewer?.renderer.setAnimationLoop(null);
    viewer?.renderer.dispose();
    // Destroying this iframe also releases its workers, cache and graphics realm.
  });
  send('ready');
})();
