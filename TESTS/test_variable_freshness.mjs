import test from 'node:test';
import assert from 'node:assert/strict';
import { freshness, coverageAge, visibleRows } from '../INTERFACE/variableFreshness.js';
const now = Date.parse('2026-09-14T00:00:00Z');
const row = { id: 'rain', label: 'Precipitation', collection: 'Basin observations', source: 'TerraClimate', layer: 2,
  status: 'available', interval_days: 30, last_updated: '2026-09-14T00:00:00Z', coverage_to: '2024-12' };

test('freshness is a bounded age score and decays through green, amber and red', () => {
  assert.equal(freshness(row, now).score, 100);
  assert.equal(freshness(row, now + 15 * 86400000).state, 'aging');
  assert.equal(freshness(row, now + 29 * 86400000).state, 'overdue');
  assert.equal(freshness(row, now + 100 * 86400000).score, 0);
});
test('unknown dates and future timestamps cannot masquerade as fresh', () => {
  for (const last_updated of [null, '', 'invalid', '2027-01-01']) assert.equal(freshness({ ...row, last_updated }, now).score, null);
  assert.equal(freshness({ ...row, interval_days: null }, now).score, null);
});
test('reference, archival and on-demand products do not decay', () => {
  for (const status of ['reference', 'archival', 'on_demand']) assert.equal(freshness({ ...row, status }, now).score, null);
  assert.equal(freshness({ ...row, status: 'missing' }, now).score, 0);
});
test('a fresh extraction with old coverage still needs attention', () => {
  assert.equal(freshness(row, now).state, 'fresh');
  assert.equal(coverageAge(row, now).behind, true);
  assert.equal(visibleRows([row], { status: 'attention' }, now).length, 1);
  assert.equal(coverageAge({ ...row, status: 'archival' }, now), null);
  assert.equal(coverageAge({ ...row, coverage_to: '2026-09' }, now), null);
});
test('search and filters preserve variable identity and cover every layer', () => {
  const rows = [row, { ...row, id: 'elevation', label: 'Elevation', layer: 1, source: 'SRTM', status: 'reference' }];
  assert.deepEqual(visibleRows(rows, { layer: '2', query: 'terraclimate' }, now), [row]);
  assert.equal(visibleRows(rows, { layer: '1', query: 'rain' }, now).length, 0);
});
