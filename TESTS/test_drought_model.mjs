import test from 'node:test';
import assert from 'node:assert/strict';
import { droughtOutlook, nextYearChance, normalsOf, presentConditions, standing, waterYearOf } from '../INTERFACE/droughtModel.js';

// Twelve complete years of 10 mm a month, observed, then an estimate that is dry.
function record({ estimateMonths = 8, estimateValue = 2 } = {}) {
  const rows = [];
  for (let year = 2010; year <= 2021; year += 1) {
    for (let month = 1; month <= 12; month += 1) rows.push({ year, month, value: 10 + (year % 3), source: 'observed', errorP90: null });
  }
  for (let offset = 0; offset < estimateMonths; offset += 1) {
    const year = 2022 + Math.floor(offset / 12), month = (offset % 12) + 1;
    rows.push({ year, month, value: estimateValue, source: 'estimated_v1.0', errorP90: 1 });
  }
  return rows;
}

test('the present is the latest month of the continued series, not the end of the observed record', () => {
  const state = presentConditions(record(), { extensive: true });
  assert.equal(state.latest, '2022-08');
  assert.equal(state.lastObserved, '2021-12');
  assert.equal(state.estimatedMonths, 8);
  assert.equal(state.month.source, 'estimated_v1.0');
  assert.equal(state.month.errorP90, 1);
  assert.equal(state.month.percentile, 0);
  assert.equal(state.month.standing, 'lowest tenth of the record');
  // The baseline is the observed record only.
  assert.deepEqual(state.baseline, { firstYear: 2010, lastYear: 2021, years: 12 });
});

test('the last twelve months join observed and estimated months and bound the estimate error', () => {
  const window = presentConditions(record(), { extensive: true }).lastTwelveMonths;
  assert.equal(window.from, '2021-09');
  assert.equal(window.months, 12);
  assert.equal(window.estimatedMonths, 8);
  assert.equal(window.errorBound, 8);
  assert.ok(window.anomalyPercent < 0);
});

test('the water year to date runs from October and is ranked among earlier water years', () => {
  const toDate = presentConditions(record(), { extensive: true }).waterYearToDate;
  assert.equal(toDate.waterYear, 2022);
  assert.equal(toDate.from, '2021-10');
  assert.equal(toDate.months, 11);
  assert.equal(toDate.comparedYears, 11);
  assert.equal(toDate.percentile, 0);
  assert.equal(toDate.dry, true);
  assert.equal(waterYearOf(2021, 10), 2022);
  assert.equal(waterYearOf(2022, 9), 2022);
});

test('an intensive variable is averaged and never given a percent anomaly', () => {
  const state = presentConditions(record(), { extensive: false });
  assert.equal(state.month.anomalyPercent, null);
  // The last observed year, 2021, is 12 mm a month.
  assert.equal(state.lastTwelveMonths.value, (4 * 12 + 8 * 2) / 12);
});

test('a gap in the window leaves the window out rather than summing across it', () => {
  const rows = record().filter(row => !(row.year === 2022 && row.month === 3));
  assert.equal(presentConditions(rows, { extensive: true }).lastTwelveMonths, null);
});

test('normals need ten complete years', () => {
  assert.equal(normalsOf(record().slice(0, 9 * 12)), null);
  assert.equal(normalsOf(record()).years, 12);
  assert.equal(standing(50), 'near normal');
});

function droughtRecord(spis) {
  return {
    fields: ['water_year', 'spi12', 'pdsi', 'ppt_anom_pct_wmo', 'up_spi12', 'up_ppt_anom_pct_wmo', 'up_q_anom_pct_wmo'],
    rows: spis.map((spi, index) => [1961 + index, spi, spi * 2, spi * 10, spi, spi * 10, spi * 12]),
  };
}

test('drought frequency, persistence and the run of below-normal years come from the record', () => {
  // 1961-2025: every fifth year dry, and each dry year followed by another dry one.
  const spis = Array.from({ length: 65 }, (_, index) => (index % 5 === 3 || index % 5 === 4 ? -1.6 : 0.4));
  const outlook = droughtOutlook(droughtRecord(spis));
  assert.equal(outlook.record.to, 2025);
  assert.equal(outlook.recent.years, 35);
  assert.equal(outlook.recent.dry, 14);
  assert.equal(outlook.recent.severe, 14);
  // After a dry year: half were followed by a dry year (the first of each pair).
  assert.equal(outlook.afterDry.years, 25); // 2025 is dry and has no next year yet
  assert.equal(outlook.afterDry.dry, 13);
  assert.equal(outlook.last.dry, true);
  assert.equal(outlook.belowNormalRun, 2);
  assert.equal(outlook.trend.direction, 'no detectable trend');
});

test('a drying record is reported as drying', () => {
  const spis = Array.from({ length: 65 }, (_, index) => 1.5 - index * 0.05);
  const outlook = droughtOutlook(droughtRecord(spis), 'upstream');
  assert.equal(outlook.trend.direction, 'drying');
  assert.ok(outlook.trend.pointsPerDecade < 0);
  assert.ok(outlook.recent.dryShare > outlook.early.dryShare);
});

test('the next-year chance conditions on the current water year once most of it has passed', () => {
  const spis = Array.from({ length: 65 }, (_, index) => (index % 4 === 0 ? -1.2 : 0.3));
  const outlook = droughtOutlook(droughtRecord(spis));
  const current = { waterYear: 2026, months: 11, percentile: 5, dry: true };
  const chance = nextYearChance(outlook, current);
  assert.equal(chance.from, 'current water year to date');
  assert.equal(chance.forWaterYear, 2027);
  assert.equal(chance.dry, true);
  assert.equal(chance.years, outlook.afterDry.years);
  // Too little of the water year has passed: the last complete year decides.
  const early = nextYearChance(outlook, { ...current, months: 3 });
  assert.equal(early.from, 'last complete water year');
  assert.equal(early.forWaterYear, 2026);
});

test('a record too short for frequencies gives no outlook', () => {
  assert.equal(droughtOutlook(droughtRecord([0.1, -1.2, 0.3])), null);
  assert.equal(nextYearChance(null, null), null);
});

test('an estimate inside its own error of normal is given no standing, and a near-zero normal no percentage', () => {
  // A dry month: most years record nothing. The estimate is a trace with a large error.
  const rows = [];
  for (let year = 2010; year <= 2021; year += 1) {
    for (let month = 1; month <= 12; month += 1) rows.push({ year, month, value: month === 8 && year % 4 === 0 ? 0.2 : 0, source: 'observed' });
  }
  for (let month = 1; month <= 8; month += 1) rows.push({ year: 2022, month, value: month === 8 ? 0.03 : 0, source: 'estimated_v1.0', errorP90: 8 });
  const { month } = presentConditions(rows, { extensive: true });
  assert.equal(month.withinError, true);
  assert.equal(month.standing, 'not distinguishable from normal');
  assert.equal(month.anomalyPercent, null);
  // Ties count half: nine dry Augusts and a trace sit near the middle, not at the top.
  assert.ok(month.percentile < 80);
});

test('a history file continued by its estimate reaches the estimate and never overwrites an observation', async () => {
  const { historySeries } = await import('../INTERFACE/continuationModel.js');
  const history = { years: [2023, 2024], series: { pre_mm_s: { values: [...Array(12).fill(5), ...Array(10).fill(6), null, null] } } };
  const document = {
    row_fields: ['year', 'month', 'value', 'coverage_fraction', 'water_equivalent_mcm', 'holdout_abs_error_p90'],
    series: { 'estimated_v1.0:local:precipitation': { label: 'Precipitation', unit: 'mm/month', rows: [
      [2024, 10, 99, 1, null, 2], [2024, 11, 7, 1, null, 2], [2024, 12, 8, 1, null, 2], [2025, 1, 9, 1, null, 2],
    ] } },
  };
  const series = historySeries(history, 'pre_mm_s', document);
  assert.equal(series.at(-1).year, 2025);
  assert.equal(series.find(row => row.year === 2024 && row.month === 10).value, 6);
  assert.equal(series.find(row => row.year === 2024 && row.month === 11).source, 'estimated_v1.0');
  assert.equal(historySeries(history, 'pre_mm_s', null).length, 22);
});

test('percentiles read as ordinals', async () => {
  const { ordinal } = await import('../INTERFACE/droughtModel.js');
  assert.deepEqual([1, 2, 3, 4, 11, 12, 13, 21, 22, 62, 100].map(ordinal),
    ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '62nd', '100th']);
});
