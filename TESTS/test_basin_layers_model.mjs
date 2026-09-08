import assert from 'node:assert/strict';
import test from 'node:test';
import {
  cellAt, divergingColor, formatPeriod, mix, periodValues, sequentialColor, summaryStats,
  timelineFor, valueAt,
} from '../INTERFACE/basinLayersModel.js';

const series = {
  basins: {
    100: { '2024-01': { precipitation: { v: 1.5 } }, '2024-02': { precipitation: { v: 2.5, z: -1.2, c: 'dry' } } },
    200: { '2024-01': { precipitation: { v: 3.0, z: 0.4 } } },
  },
};

test('cellAt and valueAt read a basin-period-variable cell', () => {
  assert.deepEqual(cellAt(series, '100', '2024-01', 'precipitation'), { v: 1.5 });
  assert.equal(valueAt(series, '200', '2024-01', 'precipitation'), 3.0);
  assert.equal(valueAt(series, '999', '2024-01', 'precipitation'), null);
});

test('timelineFor preserves missing periods as null', () => {
  assert.deepEqual(timelineFor(series, '100', ['2023-12', '2024-01', '2024-02'], 'precipitation'), [
    { period: '2023-12', v: null, z: null, c: null },
    { period: '2024-01', v: 1.5, z: null, c: null },
    { period: '2024-02', v: 2.5, z: -1.2, c: 'dry' },
  ]);
});

test('periodValues collects every basin observed in one period', () => {
  const values = periodValues(series, '2024-01', 'precipitation');
  assert.equal(values.length, 2);
  assert.deepEqual(summaryStats(values.map(item => item.v)), { min: 1.5, max: 3.0, mean: 2.25, median: 3.0 });
});

test('mix interpolates channel by channel', () => {
  assert.equal(mix('#000000', '#ffffff', 0), '#000000');
  assert.equal(mix('#000000', '#ffffff', 1), '#ffffff');
});

test('sequentialColor maps low values toward the base and high toward the colour', () => {
  const low = sequentialColor(0, 0, 10, '#ff0000', '#000000');
  const high = sequentialColor(10, 0, 10, '#ff0000', '#000000');
  assert.notEqual(low, high);
  assert.equal(sequentialColor(null, 0, 10, '#ff0000'), null);
});

test('divergingColor picks a side by the sign of z', () => {
  const dry = divergingColor(-2, 2, '#111111', '#0000ff', '#ff0000');
  const wet = divergingColor(2, 2, '#111111', '#0000ff', '#ff0000');
  assert.notEqual(dry, wet);
  assert.equal(divergingColor(null, 2), null);
});

test('formatPeriod renders month, pentad and day grains', () => {
  assert.equal(formatPeriod('year', '2016'), '2016');
  assert.equal(formatPeriod('month', '2024-06'), '2024 \u00b7 Jun');
  assert.equal(formatPeriod('pentad', '2024-06-p3'), '2024 \u00b7 Jun \u00b7 P3');
  assert.equal(formatPeriod('day', '2024-06-03'), '2024 \u00b7 Jun \u00b7 3');
});
