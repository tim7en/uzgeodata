import test from 'node:test';
import assert from 'node:assert/strict';
import { gaugesInCatchment, snowSeasons, upstreamAttribution } from '../INTERFACE/upstreamModel.js';

// Three basins, 2003-2016 monthly: A always 10 mm, B 20 mm, C 30 mm, except the last
// water year (Oct 2015 - Sep 2016), when A is doubled and C halved.
function matrix() {
  const years = [2003, 2016], months = 14 * 12, scale = 100;
  const values = new Int32Array(3 * months);
  const base = [10, 20, 30];
  for (let b = 0; b < 3; b += 1) {
    for (let m = 0; m < months; m += 1) {
      const lastWaterYear = m >= (2015 - 2003) * 12 + 9;
      const factor = lastWaterYear ? [2, 1, 0.5][b] : 1;
      values[b * months + m] = Math.round(base[b] * factor * scale);
    }
  }
  return { index: { ids: [1, 2, 3], areas_km2: [100, 100, 200], years, months, scale, null_sentinel: -2147483648 }, values };
}

test('basin contributions add up to the catchment anomaly and name where it came from', () => {
  const { index, values } = matrix();
  const result = upstreamAttribution(index, values, [0, 1, 2], { extensive: true,
    pfafById: new Map([['1', 4611111], ['2', 4611112], ['3', 4622222]]), minimumYears: 5 });
  assert.equal(result.waterYear, 2016);
  const sum = result.basins.reduce((s, b) => s + b.contribution, 0);
  assert.ok(Math.abs(sum - result.catchment.anomaly) < 1e-9);
  // A was wetter, C drier; C is half the area, so the catchment ends up drier.
  assert.ok(result.catchment.anomaly < 0);
  assert.equal(result.groups[0].key, '4611111');
  assert.ok(result.groups.at(-1).contribution < 0 && result.groups.at(-1).key === '4622222');
});

test('a single basin has nothing to attribute', () => {
  const { index, values } = matrix();
  assert.equal(upstreamAttribution(index, values, [0], { extensive: true }), null);
});

function monthly(years, value) {
  const rows = [];
  for (let year = years[0]; year <= years[1]; year += 1) {
    for (let month = 1; month <= 12; month += 1) rows.push({ year, month, value: value(year, month) });
  }
  return rows;
}

test('a wet winter whose snowpack stayed thin is read as rain, not stored snow', () => {
  const winter = month => month >= 10 || month <= 3;
  const precipitation = monthly([2003, 2016], (year, month) => (winter(month) ? (year === 2016 || (year === 2015 && month >= 10) ? 60 : 40) : 10));
  const snow = monthly([2003, 2016], (year, month) => (month === 3 ? (year === 2016 ? 60 : 120) : 20));
  const result = snowSeasons(precipitation, snow, { minimumYears: 5 });
  const last = result.rows.at(-1);
  assert.equal(last.waterYear, 2016);
  assert.ok(last.rainAnomaly > 10 && last.snowAnomaly < 0);
  assert.match(last.reading, /fell as rain/);
  assert.equal(last.peakMonth, 3);
  assert.equal(result.snowDominated, true);
});

test('gauges are found inside the catchment basins', () => {
  const basin = { properties: { hybas_id: 42 }, geometry: { type: 'Polygon', coordinates: [[[70, 40], [71, 40], [71, 41], [70, 41], [70, 40]]] } };
  const gauges = [
    { geometry: { type: 'Point', coordinates: [70.5, 40.5] }, properties: { code: 'in', name_eng: 'Inside', ts_start: '1990-01-15', ts_end: '2019-12-15', has_ts: true, q_m3s: 5 } },
    { geometry: { type: 'Point', coordinates: [72, 40.5] }, properties: { code: 'out', name_eng: 'Outside' } },
  ];
  const found = gaugesInCatchment(gauges, [basin]);
  assert.deepEqual(found.map(g => [g.code, g.basin, g.first, g.last]), [['in', '42', '1990', '2019']]);
});

test('snow carried over from earlier years is measured and flagged', () => {
  const rain = [], swe = [];
  for (let year = 2003; year <= 2016; year++) {
    for (let month = 1; month <= 12; month++) {
      rain.push({ year, month, value: 20 });
      // 400 mm never melts; each winter adds up to 300 mm on top
      const seasonal = [1, 2, 3].includes(month) ? 300 : [12, 4].includes(month) ? 150 : 0;
      swe.push({ year, month, value: 400 + seasonal });
    }
  }
  const snow = snowSeasons(rain, swe);
  assert.ok(Math.abs(snow.carryShare - 400 / 700) < 1e-9);
  assert.match(snow.carryNote, /57% of the peak snow storage here is snow left from earlier years/);
  const plain = snowSeasons(rain, swe.map(row => ({ ...row, value: row.value - 400 })));
  assert.equal(plain.carryShare, 0);
  assert.equal(plain.carryNote, null);
});

test('where glacier snow carries over, a winter is judged by the snow it added', () => {
  const rain = [], swe = [];
  for (let year = 2003; year <= 2016; year++) {
    const added = year === 2016 ? 150 : 300;      // the last winter adds half the usual snow
    for (let month = 1; month <= 12; month++) {
      rain.push({ year, month, value: 20 });
      swe.push({ year, month, value: 400 + ([1, 2, 3].includes(month) ? added : 0) });
    }
  }
  const snow = snowSeasons(rain, swe);
  const last = snow.rows.at(-1);
  assert.equal(snow.corrected, true);
  assert.equal(last.seasonalSwe, 150);
  // judged on the 400 mm store as well, the same winter would look only ~21% low
  assert.ok(last.snowAnomaly < -45 && last.snowAnomaly > -55, `anomaly ${last.snowAnomaly}`);
  assert.match(last.statement, /the snow this winter added to modelled storage was 4\d% below average/);
  assert.match(snow.rule, /the snow each winter added/);
});
