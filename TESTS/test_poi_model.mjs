import test from 'node:test';
import assert from 'node:assert/strict';
import { aoiFeature } from '../INTERFACE/aoiModel.js';
import { annualSeries, basinUnits, currentConditions, monthlyNormals, parsePois, matchPoi, reportMembers, makePoiReport, reportMonthlyCsv } from '../INTERFACE/poiModel.js';

const monthly = (years, value) => {
  const rows = [];
  for (let y = 0; y < years; y += 1) {
    for (let m = 1; m <= 12; m += 1) {
      rows.push({ year: 2003 + y, month: m, mean_observed_area: value(y, m), observed_basins: 3,
        area_coverage_percent: 100 });
    }
  }
  return rows;
};

test('a continuation is kept beside the record, never spliced into it', async () => {
  const { continuationFor, continuationLatest, continuationCsv } =
    await import('../INTERFACE/continuationModel.js');
  // Shaped like the published per-basin file: one row per month, with the model's
  // own held-out error in the last field.
  const document = {
    row_fields: ['year', 'month', 'value', 'coverage_fraction', 'water_equivalent_mcm', 'holdout_abs_error_p90'],
    series: {
      'estimated_v1.0:local:precipitation': {
        product: 'estimated_v1.0', support: 'local', label: 'Precipitation', unit: 'mm/month',
        rows: [[2025, 1, 30, 1, null, 8], [2026, 8, 12, 1, null, 8], [2025, 2, null, 1, null, 8]],
      },
      'direct_v1.1:local:ppt': {
        product: 'direct_v1.1', support: 'local', label: 'Precipitation', unit: 'mm/month',
        rows: [[2025, 1, 31, 1, null, null]],
      },
    },
  };

  const series = continuationFor(document, 'pre_mm_s', 'local');
  assert.equal(series.estimated.rows.length, 2, 'a month with no value is not a month');
  assert.deepEqual(series.estimated.rows.map(row => row.year), [2025, 2026], 'rows arrive in time order');
  assert.ok(series.direct, 'the producer release is carried separately, under its own name');

  // ERA5-Land runoff and mean temperature already reach the present, so they have
  // no continuation and must not be given one.
  assert.equal(continuationFor(document, 'run_mm_s', 'local'), null);
  assert.equal(continuationFor(document, 'snw_pc_s', 'local'), null);

  // The estimate continues the observed statistic, so it is measured against the
  // observed baseline rather than against itself.
  const normals = { byMonth: Array.from({ length: 12 }, () => 30), samples: Array.from({ length: 12 }, () => [10, 20, 30, 40]) };
  const latest = continuationLatest(series, normals);
  assert.equal(latest.year, 2026);
  assert.equal(latest.anomaly, -18);
  assert.ok(!latest.withinError, 'an anomaly larger than the error is a signal');
  assert.ok(continuationLatest({ estimated: { rows: [{ year: 2026, month: 8, value: 26, errorP90: 8 }], unit: 'mm' } },
    normals).withinError, 'one smaller than the error is not');

  assert.equal(continuationCsv(series, 'local').length, 3, 'both products reach the download');
});

test('current conditions compare a month with the same month in the record', () => {
  // A monthly value on its own answers nothing: 40 mm is a drought in April and a
  // deluge in September, so the comparison has to be against the same calendar
  // month rather than against the record as a whole.
  const seasonal = (y, m) => 40 + 30 * Math.cos((m - 3) / 12 * 2 * Math.PI) + y * 0.8;
  const state = currentConditions(monthly(20, seasonal), { factor: 1000, unit: 'm³' });
  assert.equal(state.baseline.years, 20);
  assert.equal(state.latest.year, 2022);
  assert.ok(state.latest.normal > 0 && state.latest.value > state.latest.normal);
  assert.ok(state.latest.rankPercentile > 80, 'the warmest end of a rising series ranks high');

  // A trend of +0.8 per month is +9.6 a year on an annual sum, so 96 a decade.
  assert.ok(Math.abs(state.trend.slopePerDecade - 96) < 0.5, 'Sen slope must recover the planted trend');
  assert.equal(state.trend.direction, 'increasing');
  assert.ok(state.trend.p < 0.01);
});

test('a percent anomaly is withheld where zero is not an absence', () => {
  // Temperature has no meaningful zero, so "12% above normal" would be a statement
  // about the Celsius scale. The package says which variables have a total, and
  // that is the same distinction.
  const flat = currentConditions(monthly(15, (y, m) => 10 + m + y * 0.1), { factor: null, unit: null });
  assert.equal(flat.latest.anomalyPercent, null);
  assert.equal(flat.lastTwelveMonths.anomalyPercent, null);
  assert.equal(flat.lastTwelveMonths.aggregation, 'mean', 'intensive quantities average over the year');

  const depth = currentConditions(monthly(15, (y, m) => 10 + m + y * 0.1), { factor: 1000, unit: 'm³' });
  assert.ok(depth.latest.anomalyPercent !== null);
  assert.equal(depth.lastTwelveMonths.aggregation, 'sum');
});

test('an incomplete record reports less rather than reporting wrong', () => {
  // Nine years is not a baseline, and a year missing months is not a low year.
  const short = currentConditions(monthly(9, (y, m) => m + y), { factor: 1000, unit: 'm³' });
  assert.equal(short.baseline, null, 'fewer than ten complete years leaves the normals unstated');
  assert.equal(short.trend, null);
  assert.equal(short.latest.normal, null);
  assert.equal(short.latest.anomaly, null);

  const gapped = monthly(15, (y, m) => m + y).filter(row => !(row.year === 2016 && row.month === 7));
  const state = currentConditions(gapped, { factor: 1000, unit: 'm³' });
  assert.equal(state.trend.years, 14, 'the year with a gap is left out of the trend');
  assert.equal(monthlyNormals(gapped).years, 14);

  // A running twelve months over a gap would be a smaller number, not a drier year.
  const recentGap = monthly(15, (y, m) => m + y).filter(row => !(row.year === 2017 && row.month === 5));
  assert.equal(currentConditions(recentGap.slice(0, -6), { factor: 1000, unit: 'm³' }).lastTwelveMonths, null);

  assert.equal(annualSeries([], { factor: null }).trend, null);
  assert.equal(currentConditions([], { factor: null }), null);
});

test('a coarse basin is reported through the level-12 units inside it', () => {
  // The map draws level 7 at a regional view, and statistics are published for
  // level 12, so the report was unavailable at every zoom a reader browses at.
  // Pfafstetter ids nest by prefix, which is what makes the coarse basin
  // reportable at all: its units are the level-12 basins whose id starts with its.
  const unit = (hybas, pfaf) => ({ type: 'Feature', properties: { hybas_id: hybas, basin_level: 12, pfaf_id: pfaf } });
  const features = [
    unit(11, 461101000000), unit(12, 461101010000), unit(13, 461101100000),
    unit(21, 461200000000), { type: 'Feature', properties: { hybas_id: 7, basin_level: 7, pfaf_id: 4611010 } },
  ];
  const coarse = basinUnits(features, { basin_level: 7, hybas_id: 7, pfaf_id: 4611010 });
  assert.deepEqual(coarse.map(f => f.properties.hybas_id), [11, 12],
    'only the units whose Pfafstetter id continues the parent belong to it');
  // 461101100000 is a unit of 4611011, one digit along, and must stay out of it.
  assert.ok(!coarse.some(f => f.properties.hybas_id === 13), 'a neighbouring parent keeps its own units');

  // A level-12 basin is its own single unit, matched on the identifier rather than
  // on geometry, so a neighbour sharing a boundary cannot come with it.
  assert.deepEqual(basinUnits(features, { basin_level: 12, hybas_id: 13 }).map(f => f.properties.hybas_id), [13]);

  // A basin with no published units says so instead of reporting an empty one.
  assert.deepEqual(basinUnits(features, { basin_level: 7, hybas_id: 9, pfaf_id: 9999999 }), []);
  assert.deepEqual(basinUnits(features, { basin_level: 7, hybas_id: 9 }), [], 'no id, no units');
});

test('a basin chosen on the map reports itself, not its neighbours', () => {
  // A chosen basin is the answer, not something to match. Passing its own outline
  // back through polygon intersection would pull in every neighbour that shares a
  // boundary with it, which is why the modal skips matching for this input. The
  // model still has to place it correctly in the network.
  const square = (id, x, nextDown) => ({ type: 'Feature',
    properties: { hybas_id: id, basin_level: 12, next_down: nextDown },
    geometry: { type: 'Polygon', coordinates: [[[x, 40], [x + 1, 40], [x + 1, 41], [x, 41], [x, 40]]] } });
  const basins = [square(1, 70, 0), square(2, 71, 1), square(3, 72, 2)];
  const index = { ids: [1, 2, 3], next_down: [0, 1, 2] };

  const chosen = reportMembers(index, [basins[1]]);
  assert.deepEqual(chosen.local, [1], 'the report is about the basin that was chosen');
  assert.deepEqual([...chosen.upstream].sort(), [1, 2], 'and everything draining into it');

  // The neighbour it touches must not be dragged in with it.
  assert.ok(!chosen.local.includes(0), 'a shared boundary is not a match');

  // The headwater has nothing above it and still reports itself.
  assert.deepEqual(reportMembers(index, [basins[2]]).upstream, [2]);
});

test('an area drawn on the map is parsed like an uploaded polygon', () => {
  // The drawn ring and an uploaded polygon reach the same matcher, so they go
  // through the same validation: one parser, one set of error messages.
  const vertices = [[70, 41], [71, 41], [71, 42], [70, 42]];
  const feature = aoiFeature(vertices);
  const collection = parsePois(JSON.stringify(feature), 'drawn-area.geojson');
  assert.equal(collection.features.length, 1);
  const [parsed] = collection.features;
  assert.equal(parsed.geometry.type, 'Polygon');
  const ring = parsed.geometry.coordinates[0];
  assert.deepEqual(ring[0], ring.at(-1), 'the drawn ring must close before it is matched');
  assert.ok(parsed.properties.poi_name, 'the area is named for the report');

  // A degenerate drag - a line, or a single point - must be refused with the same
  // message an invalid upload gets, not matched against every basin it touches.
  assert.throws(() => parsePois(JSON.stringify(aoiFeature([[70, 41], [71, 41]])), 'drawn-area.geojson'));
});


const polygon = (id, x = 70, holes = []) => ({ type: 'Feature', properties: { hybas_id: id, basin_level: 12 },
  geometry: { type: 'Polygon', coordinates: [[[x, 40], [x + 1, 40], [x + 1, 41], [x, 41], [x, 40]], ...holes] } });
const point = (x, y) => ({ type: 'Feature', properties: { poi_name: 'Site' }, geometry: { type: 'Point', coordinates: [x, y] } });
const index = { ids: [1, 2, 3], next_down: [0, 1, 2], areas_km2: [2, 3, 5], months: 2, years: [2020, 2020], scale: 10,
  null_sentinel: -2147483648, series: { pre_mm_s: { meta: { label: 'Precipitation', unit: 'millimetres per month' },
    provenance_ids: [0, 0, 0], provenance: [{ source: 'test' }] } } };

test('CSV accepts quoted names, BOM, aliases, multiple points and preserves identifiers', () => {
  const data = parsePois('\uFEFFname,lon,lat\r\n"Site, А",70.5,40.5\r\n"Site ""B""",71,41\r\n', 'sites.csv');
  assert.equal(data.features.length, 2);
  assert.equal(data.features[0].properties.poi_name, 'Site, А');
  assert.equal(data.features[1].properties.poi_name, 'Site "B"');
  assert.deepEqual(data.features[0].geometry.coordinates, [70.5, 40.5]);
});

test('rejects invalid coordinates, unsupported geometries, open rings and empty files', () => {
  for (const data of [point(200, 40), point('70', 40), { ...point(70, 40), geometry: null },
    { type: 'FeatureCollection', features: [] }, { ...polygon(1), geometry: { type: 'Polygon', coordinates: [[[70, 40], [71, 40], [71, 41], [70, 41]]] } }]) {
    assert.throws(() => parsePois(JSON.stringify(data)));
  }
  assert.throws(() => parsePois('name,longitude,latitude\nSite,,40', 'test.csv'));
  assert.throws(() => parsePois(JSON.stringify({ ...polygon(1), crs: { properties: { name: 'EPSG:3857' } } })));
});

test('points match containing basins and snap only within the chosen distance', () => {
  const basins = [polygon(1)];
  assert.equal(matchPoi(point(70.5, 40.5), basins, 0).status, 'contained');
  const snapped = matchPoi(point(69.999, 40.5), basins, 0.1);
  assert.equal(snapped.status, 'snapped');
  assert.ok(snapped.distanceKm > 0.08 && snapped.distanceKm < 0.09);
  assert.deepEqual(snapped.coordinate, [70, 40.5]);
  assert.equal(matchPoi(point(69.999, 40.5), basins, 0).status, 'unmatched');
  assert.equal(matchPoi(point(0, 0), basins, 10).status, 'unmatched');
  assert.equal(matchPoi(point(70, 40), basins, 0).basins.length, 1);
});

test('polygon holes exclude interior basins and points, and multipolygons preserve every part', () => {
  const hole = [[70.2, 40.2], [70.8, 40.2], [70.8, 40.8], [70.2, 40.8], [70.2, 40.2]];
  assert.equal(matchPoi(point(70.5, 40.5), [polygon(1, 70, [hole])], 0).status, 'unmatched');
  const small = polygon(2); small.geometry.coordinates = [[[70.3, 40.3], [70.4, 40.3], [70.4, 40.4], [70.3, 40.4], [70.3, 40.3]]];
  assert.equal(matchPoi(polygon(1, 70, [hole]), [small], 0).status, 'unmatched');
  const multi = { ...polygon(1), geometry: { type: 'MultiPolygon', coordinates: [polygon(1).geometry.coordinates, polygon(2, 75).geometry.coordinates] } };
  assert.equal(matchPoi(multi, [polygon(1), polygon(2, 75)]).basins.length, 2);
});

test('overlapping upstream traces are deduplicated and missing data is never extrapolated', () => {
  const basins = [polygon(1), polygon(2, 71), polygon(3, 72)];
  const members = reportMembers(index, basins.slice(0, 2));
  assert.deepEqual(members.local, [0, 1]);
  assert.deepEqual(members.upstream, [0, 1, 2]);
  const report = makePoiReport({ feature: point(70.5, 40.5), match: { ...matchPoi(point(70.5, 40.5), basins), basins: basins.slice(0, 2) }, index,
    values: new Int32Array([100, 100, 200, 200, 300, index.null_sentinel]), variable: 'pre_mm_s',
    geometry: { features: basins }, sourceFile: 'points.csv' });
  assert.equal(report.local.rows[0].mean_observed_area, 16);
  assert.equal(report.upstream.rows[0].mean_observed_area, 23);
  assert.equal(report.upstream.rows[0].total_full_catchment, 230000);
  assert.equal(report.upstream.rows[1].mean_full_catchment, null);
  assert.equal(report.upstream.rows[1].total_full_catchment, null);
  assert.equal(report.upstream.rows[1].area_coverage_percent, 50);
  assert.equal(report.upstream_geometry.features.length, 3);
  assert.equal(report.morphology, null, 'No invented dissolved morphology for a multi-outlet polygon');
  assert.match(reportMonthlyCsv(report), /upstream,pre_mm_s/);
  assert.throws(() => reportMembers(index, [polygon(99)]), /No partial report/);
});
