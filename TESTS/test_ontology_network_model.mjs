import test from 'node:test';
import assert from 'node:assert/strict';
import {
  anomalyTimeline, buildReachNetwork, deviationSummary, levelBasinLookup,
  reachNeighborhood, resolveLevelBasin, traceReachNetwork,
} from '../INTERFACE/ontologyNetworkModel.js';

test('reach neighborhood branches upstream and follows the downstream trunk', () => {
  const graph = buildReachNetwork([
    {id: 1, nextDown: 3, upstreamKm2: 5},
    {id: 2, nextDown: 3, upstreamKm2: 8},
    {id: 3, nextDown: 4, upstreamKm2: 20},
    {id: 4, nextDown: 0, upstreamKm2: 30},
  ]);
  const view = reachNeighborhood(3, graph, {upDepth: 2, downDepth: 2});
  assert.deepEqual(new Set(view.nodes.map(node => node.id)), new Set(['1', '2', '3', '4']));
  assert.equal(view.edges.filter(edge => edge.direction === 'upstream').length, 2);
  assert.equal(view.edges.filter(edge => edge.direction === 'downstream').length, 1);
});

test('an exact trace retains every upstream branch and the whole downstream trunk', () => {
  const graph = buildReachNetwork([
    {id: 1, nextDown: 3},
    {id: 2, nextDown: 3},
    {id: 3, nextDown: 4},
    {id: 4, nextDown: 5},
    {id: 5, nextDown: 0},
    {id: 6, nextDown: 2},
  ]);
  const trace = traceReachNetwork(3, graph);
  assert.deepEqual(new Set(trace.nodes.map(node => node.id)), new Set(['1', '2', '3', '4', '5', '6']));
  assert.equal(trace.upstreamCount, 3);
  assert.equal(trace.downstreamCount, 2);
  assert.equal(trace.maxUpDepth, 2);
  assert.equal(trace.edges.length, 5);
});

test('a level-12 basin resolves to its level-7 parent by Pfafstetter prefix', () => {
  const lookup = levelBasinLookup([{properties: {PFAF_ID: 4613010, HYBAS_ID: 4070274280}}]);
  assert.equal(resolveLevelBasin({pfafId: 461301001000}, lookup), '4070274280');
});

test('anomaly timeline keeps measured z scores in time order', () => {
  const series = {basins: {'407': {
    '2026-08': {precipitation: {v: 0.2, z: -1.1, c: 'dry'}},
    '2026-07': {precipitation: {v: 0.3, z: 0.5, c: 'normal'}},
  }}};
  const points = anomalyTimeline(series, 407, 'precipitation');
  assert.deepEqual(points.map(point => point.period), ['2026-07', '2026-08']);
  assert.deepEqual(deviationSummary(points), {minimum: -1.1, maximum: 0.5, latest: -1.1, meanAbsolute: 0.8});
});
