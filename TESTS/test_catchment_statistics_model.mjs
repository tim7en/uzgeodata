// The browser reads the whole-catchment package: a byte-shuffled delta matrix of
// every level-12 basin's monthly record, traced upstream from one outlet and rolled
// up by local area. The encoding is the fragile part -- a wrong plane order or a
// delta applied across a basin boundary silently returns plausible numbers -- so the
// round trip here encodes exactly as PIPELINES/build_catchment_statistics.py does
// and asserts the decoder gives the values back, null sentinel included.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  aggregateCatchment, catchmentMembers, decodeMatrix, MORPHOLOGY_FIELDS, statisticsCsv, totalDefinition,
} from '../INTERFACE/catchmentStatisticsModel.js';

const NULL = -2147483648;

/** ids 1..5: 3 above 2 above 1, 4 also above 1, and 5 draining nowhere near them. */
const index = {
  ids: [1, 2, 3, 4, 5],
  next_down: [0, 1, 2, 1, 0],
  areas_km2: [10, 20, 30, 40, 50],
  months: 2,
  years: [2003, 2003],
  scale: 10000,
  null_sentinel: NULL,
  encoding: 'gzip-byte-shuffled-delta-int32-le-basin-major',
  series: {
    pre_mm_s: { meta: { label: 'Precipitation', unit: 'millimetres per month' } },
    tmp_dc_s: { meta: { label: 'Air temperature', unit: 'degrees Celsius' } },
    snw_pc_s: { meta: { label: 'Snow cover', unit: 'percent of area' } },
  },
};

// Per basin, per month; null is a month with no observation.
const record = [[1, 2], [3, null], [5, 6], [7, 8], [9, 10]];

/** Quantize, delta within each basin, then split the int32s into four byte planes. */
function encode(series) {
  const size = index.ids.length * index.months;
  const packed = new Int32Array(size);
  series.forEach((values, basin) => values.forEach((value, month) => {
    packed[basin * index.months + month] = value === null ? NULL : Math.round(value * index.scale);
  }));
  const deltas = new Int32Array(size);
  for (let basin = 0; basin < series.length; basin++) {
    for (let month = 0; month < index.months; month++) {
      const cell = basin * index.months + month;
      deltas[cell] = month === 0 ? packed[cell] : (packed[cell] - packed[cell - 1]) | 0;
    }
  }
  const view = new DataView(new ArrayBuffer(size * 4));
  for (let cell = 0; cell < size; cell++) view.setInt32(cell * 4, deltas[cell], true);
  const bytes = new Uint8Array(view.buffer);
  const shuffled = new Uint8Array(size * 4);
  for (let cell = 0; cell < size; cell++) {
    for (let plane = 0; plane < 4; plane++) shuffled[plane * size + cell] = bytes[cell * 4 + plane];
  }
  return shuffled;
}

const values = decodeMatrix(encode(record), index);

test('the matrix round-trips its values, its deltas and its missing months', () => {
  assert.equal(values.length, index.ids.length * index.months);
  assert.deepEqual([...values].map(v => (v === NULL ? null : v / index.scale)),
    [1, 2, 3, null, 5, 6, 7, 8, 9, 10]);
});

test('a matrix that does not match its index is refused rather than decoded', () => {
  assert.throws(() => decodeMatrix(encode(record).slice(0, 12), index), /invalid encoding or size/);
  assert.throws(() => decodeMatrix(encode(record), { ...index, encoding: 'raw-int32' }), /invalid encoding or size/);
});

test('membership follows the drainage upward and stops there', () => {
  assert.deepEqual(catchmentMembers(index, 1).sort(), [0, 1, 2, 3]);
  assert.deepEqual(catchmentMembers(index, 2).sort(), [1, 2]);
  assert.deepEqual(catchmentMembers(index, 3), [2]);       // a headwater keeps itself
  assert.deepEqual(catchmentMembers(index, 5), [4]);       // an unconnected outlet stays alone
  assert.throws(() => catchmentMembers(index, 99), /not in the published/);
});

test('monthly statistics weight by local area and report what was observed', () => {
  const result = aggregateCatchment(index, values, catchmentMembers(index, 1), 'pre_mm_s');
  assert.equal(result.areaKm2, 100);
  const [january, february] = result.rows;

  // Every basin observed: 1*10 + 3*20 + 5*30 + 7*40 = 500 mm.km2 over 100 km2.
  assert.equal(january.year, 2003);
  assert.equal(january.month, 1);
  assert.equal(january.mean_observed_area, 5);
  assert.equal(january.mean_full_catchment, 5);
  assert.equal(january.min_subbasin_value, 1);
  assert.equal(january.max_subbasin_value, 7);
  assert.equal(january.total_full_catchment, 500000);     // mm -> m3 over km2
  assert.equal(january.area_coverage_percent, 100);
  assert.equal(january.observed_basins, 4);

  // Basin 2 is missing: the covered-area mean still stands, the full one does not.
  assert.equal(february.mean_observed_area, 6.5);
  assert.equal(february.mean_full_catchment, null);
  assert.equal(february.total_full_catchment, null);
  assert.equal(february.total_observed_area, 520000);
  assert.equal(february.observed_area_km2, 80);
  assert.equal(february.area_coverage_percent, 80);
  assert.equal(february.observed_basins, 3);
  assert.equal(february.basin_count, 4);
});

test('a month with nothing observed reports null rather than zero', () => {
  const empty = decodeMatrix(encode([[null, null], [null, null], [null, null], [null, null], [null, null]]), index);
  const [january] = aggregateCatchment(index, empty, catchmentMembers(index, 1), 'pre_mm_s').rows;
  assert.equal(january.mean_observed_area, null);
  assert.equal(january.min_subbasin_value, null);
  assert.equal(january.max_subbasin_value, null);
  assert.equal(january.total_full_catchment, null);
  assert.equal(january.area_coverage_percent, 0);
});

test('aggregation refuses an empty catchment or a mismatched matrix', () => {
  assert.throws(() => aggregateCatchment(index, values, [], 'pre_mm_s'), /Invalid catchment matrix/);
  assert.throws(() => aggregateCatchment(index, values.slice(0, 4), [0], 'pre_mm_s'), /Invalid catchment matrix/);
});

test('a total is offered only where adding the quantity means something', () => {
  assert.equal(totalDefinition('pre_mm_s', 'millimetres per month').unit, 'm³');
  assert.equal(totalDefinition('pre_mm_s', 'millimetres per month').factor, 1000);
  assert.equal(totalDefinition('snw_pc_s', 'percent of area').unit, 'km²');
  assert.equal(totalDefinition('tmp_dc_s', 'degrees Celsius').factor, null);
  // The unit decides, not the name: a renamed unit must not silently keep the factor.
  assert.equal(totalDefinition('pre_mm_s', 'metres per month').factor, null);
});

test('temperature carries months and extremes but no total column', () => {
  const result = aggregateCatchment(index, values, catchmentMembers(index, 1), 'tmp_dc_s');
  assert.equal(result.total.factor, null);
  assert.equal(result.rows[0].mean_observed_area, 5);
  assert.equal(result.rows[0].total_full_catchment, null);
});

test('the CSV names its units and keeps one row per month', () => {
  const result = aggregateCatchment(index, values, catchmentMembers(index, 1), 'pre_mm_s');
  const csv = statisticsCsv(1, 'pre_mm_s', index.series.pre_mm_s.meta, result);
  const lines = csv.trim().split('\n');
  assert.equal(lines.length, 3);
  const header = lines[0].split(',');
  assert.deepEqual(header.slice(0, 6), ['outlet_hybas_id', 'variable', 'value_unit', 'total_unit', 'year', 'month']);
  assert.equal(header.length, 4 + Object.keys(result.rows[0]).length);
  assert.ok(lines[1].startsWith('1,pre_mm_s,millimetres per month,m³,2003,1,'));
  // A withheld full-catchment value leaves the cell empty; it is never written as 0.
  assert.equal(lines[2].split(',')[4 + Object.keys(result.rows[0]).indexOf('mean_full_catchment')], '');
});

test('every morphology field is published with a label a reader can act on', () => {
  assert.ok(MORPHOLOGY_FIELDS.length >= 12);
  for (const [key, label] of MORPHOLOGY_FIELDS) {
    assert.match(key, /^[a-z0-9_]+$/);
    assert.ok(label.length > 3, `${key} needs a label`);
  }
  const keys = MORPHOLOGY_FIELDS.map(([key]) => key);
  assert.equal(new Set(keys).size, keys.length);
  for (const required of ['outer_perimeter_km', 'highest_elevation_m', 'lowest_elevation_m', 'relief_m']) {
    assert.ok(keys.includes(required), `${required} is missing`);
  }
});
