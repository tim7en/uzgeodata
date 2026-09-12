import assert from 'node:assert/strict';
import test from 'node:test';
import {
  AOI_FETCH_CAP, aoiFeature, attributesCsv, basinMatches, basinListCsv, centroidOf, closeRing, csvCell,
  dictionaryCsv, exportDocument, fetchAll, historyCsv, polygonContains, ringAreaKm2, selectBasins, summarise,
} from '../INTERFACE/aoiModel.js';

const square = (x, y, size) => [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]];
const basin = (id, rings, system = 'amu_darya') => ({
  type: 'Feature',
  properties: { hybas_id: id, system_id: system, area_km2: 10, upstream_km2: 20 },
  geometry: { type: 'Polygon', coordinates: rings },
});

// A 10x10 area; basins inside, straddling its edge, outside, and one wrapping it.
const AOI = [[0, 0], [10, 0], [10, 10], [0, 10]];
const inside = basin(1, [square(2, 2, 2)]);
const straddling = basin(2, [square(9, 4, 3)], 'syr_darya');
const outside = basin(3, [square(20, 20, 2)]);
const wrapping = basin(4, [square(-5, -5, 30)]);
const holeAroundArea = basin(5, [square(-20, -20, 50), square(-2, -2, 14)]);

test('a drawn ring is closed once, and fewer than three vertices is not an area', () => {
  assert.deepEqual(closeRing(AOI).at(-1), [0, 0]);
  assert.equal(closeRing([...AOI, [0, 0]]).length, 5);
  assert.equal(closeRing([[0, 0], [1, 1]]).length, 2);
  assert.equal(aoiFeature(AOI).geometry.coordinates[0].length, 5);
});

test('touching, centre and entirely-inside rules select what they say', () => {
  const features = [inside, straddling, outside, wrapping, holeAroundArea];
  const ids = rule => selectBasins(features, AOI, rule).map(entry => entry.hybas_id);
  assert.deepEqual(ids('intersects'), ['1', '2', '4']);
  assert.deepEqual(ids('within'), ['1']);
  // The straddling basin's centre (10.5, 5.5) is outside; the wrapping one's (10, 10) is on the corner.
  assert.ok(ids('centroid').includes('1'));
  assert.ok(!ids('centroid').includes('2'));
  assert.ok(!ids('centroid').includes('3'));
});

test('an area inside a basin hole does not select that basin', () => {
  assert.equal(basinMatches(holeAroundArea.geometry, closeRing(AOI), 'intersects'), false);
  assert.equal(polygonContains(holeAroundArea.geometry.coordinates, [5, 5]), false);
});

test('multipolygon basins and centroids', () => {
  const multi = { type: 'MultiPolygon', coordinates: [[square(30, 30, 1)], [square(4, 4, 1)]] };
  assert.equal(basinMatches(multi, closeRing(AOI), 'intersects'), true);
  assert.equal(basinMatches(multi, closeRing(AOI), 'within'), false);
  assert.deepEqual(centroidOf({ type: 'Polygon', coordinates: [square(0, 0, 2)] }), [1, 1]);
});

test('area and summary are in reader units', () => {
  const degree = ringAreaKm2([[0, 0], [1, 0], [1, 1], [0, 1]]);
  assert.ok(degree > 12_200 && degree < 12_400, `one square degree at the equator, got ${degree}`);
  const summary = summarise(selectBasins([inside, straddling], AOI));
  assert.deepEqual(summary, { count: 2, areaKm2: 20, bySystem: { amu_darya: 1, syr_darya: 1 } });
  assert.ok(AOI_FETCH_CAP >= 100);
});

test('CSV escapes text, keeps a missing value empty and never writes it as zero', () => {
  assert.equal(csvCell('a,"b"'), '"a,""b"""');
  assert.equal(csvCell(null), '');
  assert.equal(csvCell(0), '0');
  assert.equal(csvCell(Number.NaN), '');
  assert.equal(basinListCsv(selectBasins([inside], AOI)), 'hybas_id,system_id,area_km2,upstream_km2\n1,amu_darya,10,20\n');
});

const catalogue = {
  attributes: ['pre_mm_s01', 'dis_m3_pyr'],
  meta: {
    pre_mm_s01: { label: 'Precipitation, January', category: 'Climate', support: 's', unit: 'mm',
      original: { dataset: 'WorldClim' }, substitute: { unit: 'mm/month', statistic: 'mean', period: ['2003-01-01', '2023-01-01'],
        source_release: 'chirps@x', method: 'derive@y' } },
    dis_m3_pyr: { label: 'Discharge, annual, pour point', category: 'Hydrology', support: 'p', unit: 'm3/s', original: { dataset: 'WaterGAP' } },
  },
  reading: { substitute: 'not a reproduction' },
};
const records = [{ basin_id: '1', system: 'amu_darya', area_km2: 10, original: [12, 0.4], substitute: [11.5, null] }];
const histories = [{ basin_id: '1', years: [2003, 2003], series: { pre_mm_s: { unit: 'mm', values: [1, null, ...Array(10).fill(2)] } } }];

test('attribute table pairs each published value with its estimate', () => {
  const [header, row] = attributesCsv(catalogue, records).trim().split('\n');
  assert.equal(header, 'hybas_id,system_id,area_km2,pre_mm_s01_hydroatlas,pre_mm_s01_estimate,dis_m3_pyr_hydroatlas,dis_m3_pyr_estimate');
  assert.equal(row, '1,amu_darya,10,12,11.5,0.4,');
  const dictionary = dictionaryCsv(catalogue);
  assert.match(dictionary, /pre_mm_s01,"Precipitation, January",Climate,sub-basin,mm,WorldClim,mm\/month,mean,2003-01-01,2023-01-01,chirps@x,derive@y/);
  assert.match(dictionary, /dis_m3_pyr,"Discharge, annual, pour point",Hydrology,pour point,/);
});

test('monthly table is long, dated, and leaves a missing month empty', () => {
  const lines = historyCsv(histories).trim().split('\n');
  assert.equal(lines[0], 'hybas_id,series,unit,year,month,value');
  assert.equal(lines.length, 13);
  assert.equal(lines[1], '1,pre_mm_s,mm,2003,1,1');
  assert.equal(lines[2], '1,pre_mm_s,mm,2003,2,');
});

test('the JSON export carries the area, rule, provenance and every basin', () => {
  const basins = selectBasins([inside, straddling], AOI);
  const document = exportDocument({ vertices: AOI, rule: 'intersects', basins, catalogue, records, histories,
    release: { commit: 'abc' }, generatedAt: '2026-09-13T00:00:00Z' });
  assert.equal(document.area_of_interest.geometry.type, 'Polygon');
  assert.equal(document.selection.rule, 'intersects');
  assert.equal(document.release.commit, 'abc');
  assert.equal(document.basins.length, 2);
  assert.deepEqual(document.basins[0].estimate, [11.5, null]);
  assert.equal(document.basins[1].estimate, undefined, 'a basin without a fetched record carries no invented values');
  assert.equal(document.basins[0].monthly.series.pre_mm_s.values[1], null);
  assert.equal(JSON.parse(JSON.stringify(document)).basins[0].feature, undefined, 'geometry of the basins is not duplicated');
});

test('fetchAll reports failures and non-JSON answers instead of stopping or hiding them', async () => {
  const fetcher = async url => {
    if (url === 'missing') return { ok: false, status: 404, headers: new Map([['content-type', 'text/html']]) };
    if (url === 'shell') return { ok: true, status: 200, headers: new Map([['content-type', 'text/html']]), json: async () => ({}) };
    return { ok: true, status: 200, headers: new Map([['content-type', 'application/json']]), json: async () => ({ url }) };
  };
  const progress = [];
  const { results, failures } = await fetchAll(['a', 'missing', 'b', 'shell'], { concurrency: 2, fetcher, onProgress: done => progress.push(done) });
  assert.deepEqual(results[0], { url: 'a' });
  assert.deepEqual(results[2], { url: 'b' });
  assert.deepEqual(failures.map(failure => failure.url).sort(), ['missing', 'shell']);
  assert.equal(progress.at(-1), 4);
});
