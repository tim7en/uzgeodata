import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
  anomalyTimeline, buildReachNetwork, deviationSummary, findHydroEntities, levelBasinLookup,
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

test('entity search resolves a Pfafstetter code as a basin before reach matches', () => {
  const results = findHydroEntities('462172411000',
    [{id: '40301481', basinId: '4120396550'}],
    [{id: 4120396550, pfafId: 462172411000, order: 3}]);
  assert.equal(results.length, 1);
  assert.equal(results[0].type, 'basin');
  assert.equal(results[0].record.id, 4120396550);
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

test('a level-7 unit outside Uzbekistan is searchable in the natural frame', () => {
  // The trace view searches every level of the natural frame at once: an id in a
  // reader's hand does not say whether it names a level-7, 10 or 12 unit.
  const network = JSON.parse(readFileSync(
    new URL('../PUBLISHED/data/hydroclimate/basin-network.json', import.meta.url), 'utf8'));
  const basins = Object.values(network.levels).flatMap(entry => entry.basins);
  const byId = new Map(basins.map(basin => [String(basin.id), basin]));
  assert.equal(basins.length, network.counts.units);

  const matches = findHydroEntities('4070529600', [], basins);
  assert.equal(matches[0].type, 'basin');
  assert.equal(String(matches[0].record.id), '4070529600');
  assert.equal(matches[0].record.pfafId, 4619503);

  // Searching the Pfafstetter code finds the same unit.
  assert.ok(findHydroEntities('4619503', [], basins).some(hit => String(hit.record.id) === '4070529600'));
  // A level-10 and a level-12 id resolve in the same search.
  assert.ok(byId.has(String(network.controlSections.find(section => section.level === 10).id)));
  assert.ok(byId.has(String(network.controlSections.find(section => section.level === 12).id)));
});

test('the natural frame traces upstream past the national border', () => {
  const network = JSON.parse(readFileSync(
    new URL('../PUBLISHED/data/hydroclimate/basin-network.json', import.meta.url), 'utf8'));
  const level7 = network.levels['7'].basins;
  const graph = buildReachNetwork(level7);
  const focus = String(network.defaultFocus.id);
  const view = traceReachNetwork(focus, graph);
  // The Amu control section drains 86 level-7 units; the clipped national
  // network could reach none of them.
  assert.ok(view.upstreamCount >= 80, `expected a deep upstream trace, got ${view.upstreamCount}`);
  assert.ok(view.nodes.some(node => node.id === '4070529600'));
});
