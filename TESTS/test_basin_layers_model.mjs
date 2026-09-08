import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {
  cellAt, divergingColor, formatPeriod, frameTitle, mix, periodLabel, periodValues, scopeLabel,
  sequentialColor, summaryStats, timelineFor, unitLabel, valueAt,
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

test('a layer card names its frame, its units and its periods separately', () => {
  const layer = {
    spatialScope: 'headwater_formation', spatialUnit: 'HydroATLAS level-7 subbasin',
    periodGrain: 'month', coverage: {basins: 121, periods: 10},
  };
  assert.equal(scopeLabel(layer.spatialScope), 'Upper Amu + Upper Syr \u00b7 runoff formation');
  assert.equal(unitLabel(layer), '121 subbasins');
  assert.equal(periodLabel(layer), '10 monthly periods');
  assert.equal(frameTitle(layer), 'Upper Amu + Upper Syr formation zones');
});

test('a single unit or period is not labelled as a plural', () => {
  assert.equal(periodLabel({periodGrain: 'month', coverage: {periods: 1}}), '1 monthly period');
  assert.equal(periodLabel({periodGrain: 'year', coverage: {periods: 1}}), '1 year');
  assert.equal(periodLabel({periodGrain: 'day', coverage: {periods: 332}}), '332 daily dates');
  assert.equal(unitLabel({spatialUnit: 'headwater formation system', coverage: {basins: 2}}), '2 formation systems');
  assert.equal(unitLabel({spatialUnit: 'HydroATLAS level-12 basin', coverage: {basins: 3863}}), '3,863 basins');
});

test('an undeclared scope degrades to readable words rather than a slug', () => {
  assert.equal(scopeLabel('some_new_scope'), 'some new scope');
  assert.equal(scopeLabel(undefined), 'scope not declared');
  assert.equal(frameTitle({spatialScope: 'full_basin'}), 'Amu Darya + Syr Darya basin frame');
});

test('every published layer resolves to a curated frame label', () => {
  const index = JSON.parse(readFileSync(
    new URL('../PUBLISHED/data/basin-layers/index.json', import.meta.url), 'utf8'));
  assert.ok(index.layers.length >= 10);
  for (const layer of index.layers) {
    // A raw slug reaching the card means a scope was added without a label.
    assert.ok(!scopeLabel(layer.spatialScope).includes('_'), `${layer.id} has no curated scope label`);
    assert.ok(!frameTitle(layer).includes('_'), `${layer.id} has no curated frame title`);
    assert.match(unitLabel(layer), /^[\d,]+ [a-z ]+$/);
    assert.match(periodLabel(layer), /^[\d,]+ [a-z ]+$/);
  }
  // The transboundary and national frames must stay distinguishable in the list.
  const scopes = new Set(index.layers.map(layer => layer.spatialScope));
  assert.ok(scopes.has('national_intersection'));
  assert.ok(scopes.has('headwater_formation') || scopes.has('full_basin'));
});
