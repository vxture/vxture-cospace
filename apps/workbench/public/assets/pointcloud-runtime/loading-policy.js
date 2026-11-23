/* Optional hints to Potree's native loader; never a second node scheduler. */
export const STRATEGIES = ['baseline', 'task', 'adaptive', 'governance', 'combined'];
export const BASELINE = Object.freeze({points: 500000, nodePixels: 30, loads: 4});

export class LoadingPolicy {
  constructor(strategy = 'baseline') {
    this.strategy = STRATEGIES.includes(strategy) ? strategy : 'baseline';
    this.task = ['task', 'combined'].includes(this.strategy);
    this.adaptive = ['adaptive', 'combined'].includes(this.strategy);
    this.governance = ['governance', 'combined'].includes(this.strategy);
    this.network = null;
    this.disabled = false;
  }
  observeNetwork(bytes, elapsed, ttfb) {
    if (![bytes, elapsed, ttfb].every(Number.isFinite) || bytes <= 0 || elapsed <= 0 || ttfb < 0) return;
    const sample = {bytes, elapsed, ttfb};
    this.network = this.network ? Object.fromEntries(Object.keys(sample).map(k => [k, this.network[k] * .75 + sample[k] * .25])) : sample;
  }
  budget({moving = false, hidden = false, browsing = true, frameMs = 0, decoding = 0} = {}) {
    if (this.disabled) return {...BASELINE, freeze: false};
    let loads = BASELINE.loads;
    if (this.adaptive && this.network) {
      // Small, latency-bound ranges can use more slots; large transfers and
      // decoder pressure use fewer. Final stable-view geometry stays unchanged.
      const n = this.network;
      loads = n.bytes < 65536 && n.ttfb > n.elapsed * .5 ? 6 : n.bytes > 262144 && n.elapsed > 250 ? 2 : 4;
      if (frameMs > 33.3 || decoding >= 4) loads = Math.min(loads, 2);
    }
    if (this.governance && moving) loads = 1;
    return {points: this.adaptive && moving ? 250000 : BASELINE.points,
      nodePixels: this.adaptive && moving ? 60 : BASELINE.nodePixels, loads,
      freeze: this.governance && (hidden || !browsing)};
  }
  disable() { this.disabled = true; }
}

export class TransferLedger {
  constructor(limit = 8192) {
    this.limit = limit;
    this.ranges = new Map();
    this.bytes = 0;
    this.repeatedBytes = 0;
    this.complete = true;
  }
  received(key, bytes) {
    if (!Number.isSafeInteger(bytes) || bytes <= 0) return;
    this.bytes += bytes;
    const previous = this.ranges.get(key);
    if (previous) {
      this.repeatedBytes += bytes;
      previous.unused += bytes;
    } else if (this.ranges.size < this.limit) this.ranges.set(key, {unused: bytes});
    else this.complete = false;
  }
  rendered(key) {
    const value = this.ranges.get(key);
    if (value) value.unused = 0;
  }
  snapshot() {
    return {octree_bytes: this.bytes, unused_bytes: [...this.ranges.values()].reduce((sum, v) => sum + v.unused, 0),
      repeated_bytes: this.repeatedBytes, accounting_complete: this.complete};
  }
}

export function percentile(values, fraction) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * fraction) - 1)];
}
