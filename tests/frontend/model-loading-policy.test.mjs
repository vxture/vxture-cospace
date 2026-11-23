import test from 'node:test';
import assert from 'node:assert/strict';
import {LoadingPolicy, TransferLedger, BASELINE, percentile} from '../../apps/workbench/public/assets/pointcloud-runtime/loading-policy.js';

test('mature baseline and independent switches preserve final quality', () => {
  for (const strategy of ['baseline', 'task', 'adaptive', 'governance', 'combined', 'unknown']) {
    const p = new LoadingPolicy(strategy);
    assert.equal(p.budget().points, BASELINE.points);
    assert.equal(p.budget().nodePixels, BASELINE.nodePixels);
    assert.equal(p.task, ['task', 'combined'].includes(strategy));
    assert.equal(p.adaptive, ['adaptive', 'combined'].includes(strategy));
    assert.equal(p.governance, ['governance', 'combined'].includes(strategy));
  }
});

test('adaptive motion quality must recover before the same view can be ready', () => {
  const p = new LoadingPolicy('adaptive');
  p.observeNetwork(500000, 900, 100);
  assert.equal(p.budget({moving: true}).points, 250000);
  assert.equal(p.budget({moving: true}).loads, 2);
  assert.deepEqual(p.budget(), {...BASELINE, loads: 2, freeze: false});
  const small = new LoadingPolicy('adaptive');
  small.observeNetwork(10000, 120, 100);
  assert.equal(small.budget().loads, 6);
  assert.equal(small.budget({decoding: 5}).loads, 2);
  assert.equal(small.budget({frameMs: 50}).loads, 2);
  small.observeNetwork(Infinity, 1, 0);
  assert.equal(small.budget().loads, 6);
});

test('governance pauses native selection, retains inflight data, and resumes without lower quality', () => {
  const p = new LoadingPolicy('governance');
  assert.equal(p.budget({hidden: true}).freeze, true);
  assert.equal(p.budget({browsing: false}).freeze, true);
  assert.equal(p.budget({moving: true}).loads, 1);
  assert.deepEqual(p.budget(), {...BASELINE, freeze: false});
  p.disable();
  assert.deepEqual(p.budget({moving: true, hidden: true}), {...BASELINE, freeze: false});
});

test('range accounting distinguishes repeated transfers and never counts an old visible frame as new use', () => {
  const ledger = new TransferLedger(2);
  ledger.received('bytes=0-99', 100);
  ledger.rendered('bytes=0-99');
  ledger.received('bytes=0-99', 100);
  ledger.received('bytes=100-149', 50);
  assert.deepEqual(ledger.snapshot(), {octree_bytes: 250, unused_bytes: 150, repeated_bytes: 100, accounting_complete: true});
  ledger.rendered('bytes=0-99');
  assert.equal(ledger.snapshot().unused_bytes, 50);
  ledger.received('bytes=200-299', 100);
  assert.equal(ledger.snapshot().accounting_complete, false);
  assert.equal(ledger.ranges.size, 2);
});

test('frame percentile retains long interactive frames rather than averaging them away', () => {
  assert.equal(percentile([...Array(90).fill(16), ...Array(10).fill(70)], .95), 70);
  assert.equal(percentile([], .95), 0);
});
