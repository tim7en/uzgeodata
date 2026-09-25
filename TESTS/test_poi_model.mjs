import test from 'node:test';
import assert from 'node:assert/strict';
import { parsePois, matchPoi, reportMembers, makePoiReport, reportMonthlyCsv } from '../INTERFACE/poiModel.js';

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
