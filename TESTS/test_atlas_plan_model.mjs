import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {
  batchCount, clamp, minutes, rowsPerMonth, runtimeHours, snapshotValues, tableRows,
} from '../INTERFACE/atlasPlanModel.js';

const plan = JSON.parse(readFileSync(
  new URL('../PUBLISHED/data/atlas/implementation-plan.json', import.meta.url), 'utf8'));
const {domain_basins: basins} = plan.runtime;

test('a storage scenario is one row per basin, indicator and month', () => {
  assert.equal(tableRows(basins, 10, 1), 893_400);
  assert.equal(tableRows(basins, 10, 27), 893_400 * 27);
  assert.equal(rowsPerMonth(basins, 10), basins * 10);
  assert.equal(snapshotValues(basins, 196), basins * 196);
  assert.equal(tableRows(basins, 1, 1) / 12, rowsPerMonth(basins, 1));
});

test('a runtime estimate stays absent until a batch has actually been measured', () => {
  assert.equal(runtimeHours(basins, 200, ''), null, 'nothing measured, nothing shown');
  assert.equal(runtimeHours(basins, 200, 0), null);
  assert.equal(runtimeHours(basins, 200, -5), null);
  assert.equal(runtimeHours(basins, 200, 'soon'), null);
  assert.equal(Number(runtimeHours(basins, 200, 10).toFixed(1)), 6.3);
});

test('a partial batch still has to run', () => {
  assert.equal(batchCount(basins, 200), 38);
  assert.equal(batchCount(basins, basins), 1);
  assert.equal(batchCount(basins, basins - 1), 2);
  assert.equal(batchCount(10, 3), 4);
});

test('an out-of-range or unreadable input falls back inside its bounds', () => {
  assert.equal(clamp(10, 1, 281), 10);
  assert.equal(clamp(0, 1, 281), 1);
  assert.equal(clamp(9999, 1, 281), 281);
  assert.equal(clamp('', 1, 281), 1);
  assert.equal(clamp('abc', 1, 281), 1);
  assert.equal(clamp(NaN, 1, 100), 1);
});

test('the pilot timings are reported in the units the page labels them with', () => {
  assert.equal(minutes(plan.runtime.pilot_cold_seconds), plan.runtime.pilot_cold_seconds / 60);
  assert.ok(minutes(plan.runtime.pilot_cold_seconds) < 4, 'the cold pilot is minutes, not hours');
});
