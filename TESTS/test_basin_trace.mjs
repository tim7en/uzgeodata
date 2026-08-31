// Guard rails for the upstream trace and the attribute arithmetic behind the
// basin tables. Run with `npm run test:trace`.
//
// The last two cases are the ones that matter: they pin the two ways a naive
// roll-up gets a catchment wrong — averaging a column that already integrates
// the upstream area, and averaging class codes into a code that decodes to
// nothing.

import assert from 'node:assert/strict';
import test from 'node:test';
import {
  aggregateColumn, buildUpstreamMap, traceCoverage, traceUpstream,
} from '../INTERFACE/basinTrace.js';

//   4 -> 2 -> 1        the outlet is 1, and 5 hangs off 3
//   5 -> 3 -> 1
const NETWORK = [
  { id: 1, nextDown: 0, areaKm2: 100, uzbekistanKm2: 100, upstreamKm2: 1000 },
  { id: 2, nextDown: 1, areaKm2: 50, uzbekistanKm2: 50, upstreamKm2: 200 },
  { id: 3, nextDown: 1, areaKm2: 30, uzbekistanKm2: 10, upstreamKm2: 90 },
  { id: 4, nextDown: 2, areaKm2: 20, uzbekistanKm2: 20, upstreamKm2: 20 },
  { id: 5, nextDown: 3, areaKm2: 10, uzbekistanKm2: 0, upstreamKm2: 10 },
];
const upstream = buildUpstreamMap(NETWORK);
const records = new Map(NETWORK.map(basin => [basin.id, basin]));
const weights = new Map(NETWORK.map(basin => [basin.id, basin.uzbekistanKm2]));
const index = new Map([1, 2, 3, 4, 5].map((id, position) => [id, position]));

test('a trace collects the whole upstream tree and reports its depth', () => {
  const { ids, depth } = traceUpstream(1, upstream);
  assert.deepEqual([...ids].sort(), [1, 2, 3, 4, 5]);
  assert.equal(depth, 2);
});

test('a headwater basin traces to itself alone', () => {
  assert.deepEqual([...traceUpstream(4, upstream).ids], [4]);
});

test('a trace from midstream excludes the other tributary', () => {
  assert.deepEqual([...traceUpstream(2, upstream).ids].sort(), [2, 4]);
});

test('a cycle terminates instead of hanging', () => {
  const looped = buildUpstreamMap([
    { id: 1, nextDown: 2 }, { id: 2, nextDown: 1 },
  ]);
  assert.deepEqual([...traceUpstream(1, looped).ids].sort(), [1, 2]);
});

test('coverage separates what was traced from what is really upstream', () => {
  const { ids } = traceUpstream(1, upstream);
  const coverage = traceCoverage(ids, records, records.get(1));
  assert.equal(coverage.basins, 5);
  assert.equal(coverage.catchmentKm2, 210);   // every sub-basin area
  assert.equal(coverage.uzbekistanKm2, 180);  // the parts inside the border
  assert.equal(coverage.reportedKm2, 1000);   // what HydroSHEDS says is up there
  assert.equal(coverage.coverage, 0.21);      // so the trace is a fifth of it
});

test('an area-weighted mean weights by area inside the country', () => {
  const { ids } = traceUpstream(1, upstream);
  const column = [10, 20, 30, 40, 50];
  // Basin 5 has no area in Uzbekistan, so it carries no weight at all.
  const expected = (10 * 100 + 20 * 50 + 30 * 10 + 40 * 20 + 50 * 0) / 180;
  const result = aggregateColumn('areaWeightedMean', ids, 1, index, column, weights);
  assert.equal(result.value, expected);
  assert.equal(result.basins, 5);
});

test('a null drops out of both the total and the weight', () => {
  const { ids } = traceUpstream(1, upstream);
  const column = [10, null, 30, 40, 50];
  // Basin 2's null leaves the weight entirely. Basin 5 still carries a value, so
  // it is counted even though its zero weight keeps it out of the mean.
  const expected = (10 * 100 + 30 * 10 + 40 * 20) / (100 + 10 + 20);
  const result = aggregateColumn('areaWeightedMean', ids, 1, index, column, weights);
  assert.equal(result.value, expected);
  assert.equal(result.basins, 4, 'reports how many basins actually carried a value');
});

test('an upstream-integrated column is read at the outlet, never averaged', () => {
  const { ids } = traceUpstream(1, upstream);
  // Population upstream: the outlet already counts everyone. Averaging these
  // would report 300 — a figure describing no place at all.
  const column = [1000, 200, 90, 20, 10];
  const result = aggregateColumn('outlet', ids, 1, index, column, weights);
  assert.equal(result.value, 1000);
  assert.equal(result.basins, 1);
});

test('a majority class takes the class holding the most area, not the mean', () => {
  const { ids } = traceUpstream(1, upstream);
  //  class 7 holds basin 1 (100 km2); class 2 holds basins 2,3,4 (80 km2).
  const column = [7, 2, 2, 2, 2];
  const result = aggregateColumn('majority', ids, 1, index, column, weights);
  assert.equal(result.value, 7, 'the mean would be 3, which is not a class present');
  assert.equal(result.basins, 5);
});

test('an outlet with no atlas match yields no value rather than a wrong one', () => {
  const { ids } = traceUpstream(1, upstream);
  const result = aggregateColumn('outlet', ids, 99, index, [1, 2, 3, 4, 5], weights);
  assert.equal(result.value, null);
  assert.equal(result.basins, 0);
});

// Basin 1 straddles two provinces, 2 and 4 sit wholly in one, 3 in another, and
// 5 has no overlay row at all — the case a basin outside the boundary produces.
const OVERLAY = {
  1: { adm1: { UZ27: 60, UZ26: 40 } },
  2: { adm1: { UZ27: 50 } },
  3: { adm1: { UZ03: 30 } },
  4: { adm1: { UZ27: 20 } },
};

test('administrative contributions are summed and ranked by area', async () => {
  const { aggregateAdmin } = await import('../INTERFACE/basinTrace.js');
  const { ids } = traceUpstream(1, upstream);
  const { units, sharedKm2 } = aggregateAdmin(ids, OVERLAY, 'adm1');
  assert.equal(sharedKm2, 200, 'basin 5 contributes nothing, having no overlay row');
  assert.deepEqual(units.map(u => u.pcode), ['UZ27', 'UZ26', 'UZ03'], 'ranked by area, not by name');
  assert.equal(units[0].km2, 130);       // 60 + 50 + 20
  assert.equal(units[0].share, 0.65);    // of the area the boundaries cover
  assert.equal(units.reduce((total, u) => total + u.share, 0), 1);
});

test('a trace with no administrative overlay reports nothing rather than zero-dividing', async () => {
  const { aggregateAdmin } = await import('../INTERFACE/basinTrace.js');
  const { units, sharedKm2 } = aggregateAdmin(new Set([5]), OVERLAY, 'adm1');
  assert.deepEqual(units, []);
  assert.equal(sharedKm2, 0);
});
