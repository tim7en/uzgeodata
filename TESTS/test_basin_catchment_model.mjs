import test from 'node:test';
import assert from 'node:assert/strict';
import { basinCatchment } from '../INTERFACE/basinCatchmentModel.js';

const feature = (id, next, level = 12) => ({
  type: 'Feature', properties: { hybas_id: id, next_down: next, basin_level: level, area_km2: 10 },
  geometry: { type: 'Polygon', coordinates: [[[Number(id), 0], [Number(id) + 0.5, 0], [Number(id), 1], [Number(id), 0]]] },
});
const collection = { features: [feature(1, 0), feature(2, 1), feature('3', '2'), feature(4, 1), feature(5, 2, 7)] };

test('catchment follows upstream links and excludes downstream, sibling and other-level basins', () => {
  const result = basinCatchment(collection, { hybas_id: 2, basin_level: 12, upstream_km2: 20 });
  assert.equal(result.selected.properties.hybas_id, 2);
  assert.deepEqual(result.upstream.features.map(f => f.properties.hybas_id), ['3']);
  assert.equal(result.count, 1);
  assert.equal(result.areaKm2, 20);
  assert.deepEqual(result.bounds, [[0, 2], [1, 3.5]]);
  assert.equal(result.partial, false);
});

test('headwaters retain their selected polygon and partial coverage remains explicit', () => {
  const result = basinCatchment(collection, { hybas_id: '3', basin_level: 12, upstream_km2: 100 });
  assert.equal(result.count, 0);
  assert.equal(result.areaKm2, 10);
  assert.equal(result.partial, true);
  assert.ok(result.selectedBounds);
});

test('missing selections do not fabricate a catchment and cycles do not duplicate area', () => {
  assert.equal(basinCatchment(collection, { hybas_id: 99, basin_level: 12 }), null);
  const loop = basinCatchment({ features: [feature(1, 2), feature(2, 1)] }, { hybas_id: 1, basin_level: 12 });
  assert.equal(loop.count, 1);
  assert.equal(loop.areaKm2, 20);
});
