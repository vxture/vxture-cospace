/* Potree runs in its own realm. No platform Three objects or authentication state cross this bridge. */
(() => {
  'use strict';
  const channel = 'cospace.pointcloud/1';
  let session = '', viewer, cloud, agent, config, objects = [], firstFrame = false, disposed = false;
  let lastReport = 0, requests = 0, transferred = 0, fatal = false, paused = false, geometry = true, human = true;
  const controllers = new Set();
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
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!config || !url.pathname.includes('/display/')) return nativeFetch(input, init);
    const base = new URL(config.entry, location.origin);
    if (url.origin !== location.origin || !url.href.startsWith(base.href.slice(0, base.href.lastIndexOf('/') + 1)) || fatal || paused || disposed) {
      throw Error('display_context_changed');
    }
    const controller = new AbortController();
    controllers.add(controller);
    try {
      const callerSignal = init.signal || (input instanceof Request ? input.signal : null);
      const signal = callerSignal ? AbortSignal.any([controller.signal, callerSignal]) : controller.signal;
      const response = await nativeFetch(input, {...init, signal, credentials: 'same-origin', cache: 'no-store'});
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
        fail('部分模型数据暂不可读，已保留可用画面，请重试。');
        throw Error('display_read_failed');
      }
      // Keep cancellation attached through the body, not just until headers arrive.
      const expected = range ? Number(returned[2]) - Number(returned[1]) + 1 : Number(response.headers.get('content-length'));
      if (!Number.isSafeInteger(expected) || expected <= 0 || expected > (range ? 16 * 1024 * 1024 : 50 * 1024)) {
        await response.body?.cancel(); throw Error('display_response_budget');
      }
      const raw = await response.arrayBuffer();
      if (signal.aborted || fatal || disposed) throw new DOMException('Aborted', 'AbortError');
      if (raw.byteLength !== expected) { fail('部分模型数据不完整，已保留可用画面，请重试。'); throw Error('display_response_truncated'); }
      requests++;
      transferred += raw.byteLength;
      return new Response(raw, {status: response.status, statusText: response.statusText, headers: response.headers});
    } catch (error) {
      if (error.name !== 'AbortError' && !fatal && !disposed) fail('部分模型数据暂不可读，已保留可用画面，请重试。');
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
    if (cloud) cloud.visible = geometry && human;
    if (agent) agent.visible = geometry && !human;
  }
  function report() {
    if (!cloud || disposed) return;
    // numVisiblePoints includes queued, undecoded nodes in upstream Potree.
    // Only loaded tree nodes submitted in this completed render pass count as geometry.
    const points = !geometry ? 0 : human ? (cloud.visibleNodes || []).reduce((sum, node) =>
      sum + (node.sceneNode?.geometry?.attributes.position.count || 0), 0) : agent?.geometry.attributes.position.count || 0;
    if (!firstFrame && points > 0) {
      firstFrame = true;
      send('first-frame', {points, elapsed_ms: performance.now(), requests, transferred});
    }
    if (performance.now() - lastReport < 160) return;
    lastReport = performance.now();
    const camera = viewer.scene.getActiveCamera();
    const labels = objects.map(object => {
      const p = new THREE.Vector3(...local(object.anchor_m)).project(camera);
      return {id: object.object_id, x: (p.x + 1) / 2, y: (1 - p.y) / 2, visible: p.z >= -1 && p.z <= 1 && Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1};
    });
    send('frame', {points, loading: human ? Potree.numNodesLoading : 0, requests, transferred, labels,
      cached_points: Potree.lru.numPoints,
      geometries: viewer.renderer.info.memory.geometries});
  }
  async function start(value) {
    if (viewer || disposed) return;
    config = value;
    const entry = new URL(config.entry, location.origin);
    if (entry.origin !== location.origin || !/^\/(candidates\/build-[A-Za-z0-9-]+|publications\/preview-[a-f0-9]{16})\/display\/[a-f0-9]{64}\/metadata\.json$/.test(entry.pathname)) {
      fail('模型显示入口无效。', true); return;
    }
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
      viewer.addEventListener('render.pass.end', report);
      // 1.8.2's convenience loadPointCloud invokes OctreeLoader twice for metadata.json.
      // Use its exported native loader directly, retaining the upstream LOD/decoder.
      const loaded = await Potree.OctreeLoader.load(entry.href);
      if (disposed || fatal) return;
      cloud = new Potree.PointCloudOctree(loaded.geometry);
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
      cloud.material.pointSizeType = Potree.PointSizeType.ADAPTIVE;
      cloud.material.size = 1;
      cloud.material.shape = Potree.PointShape.CIRCLE;
      viewer.scene.addPointCloud(cloud);
      cloud.updateMatrixWorld(true);
      viewer.fitToScreen(1.1);
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
      void start(value.config);
      return;
    }
    if (value.session !== session || !viewer || disposed || fatal) return;
    if (value.type === 'retry') { paused = false; viewer.setFreeze(false); }
    if (value.type === 'reset') viewer.fitToScreen(1.1);
    if (value.type === 'focus' && Array.isArray(value.point) && value.point.length === 3 && value.point.every(Number.isFinite)) {
      const view = viewer.scene.view;
      const next = new THREE.Vector3(...local(value.point));
      const direction = view.getPivot().sub(view.position).normalize();
      const radius = Math.max(.5, Math.min(view.radius, 10));
      view.position.copy(next).addScaledVector(direction, -radius);
      view.lookAt(next);
      view.radius = radius;
    }
    if (value.type === 'settings') {
      geometry = value.geometry;
      human = value.view === 'human';
      objects = Array.isArray(value.objects) ? value.objects : [];
      apply();
    }
    if (value.type === 'agent' && value.positions instanceof ArrayBuffer) {
      if (agent) { viewer.scene.scene.remove(agent); agent.geometry.dispose(); agent.material.dispose(); }
      const g = new THREE.BufferGeometry();
      const positions = new Float64Array(value.positions);
      for (let i = 0; i < positions.length; i += 3) positions.set(local(Array.from(positions.subarray(i, i + 3))), i);
      g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
      agent = new THREE.Points(g, new THREE.PointsMaterial({size: .05, color: '#60d5ed'}));
      viewer.scene.scene.add(agent);
      apply();
    }
  });
  addEventListener('pagehide', () => {
    disposed = true;
    for (const controller of controllers) controller.abort();
    viewer?.renderer.setAnimationLoop(null);
    viewer?.renderer.dispose();
    // Destroying this iframe also releases its workers, cache and graphics realm.
  });
  send('ready');
})();
