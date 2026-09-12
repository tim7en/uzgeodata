// Area of interest: a polygon a reader draws, the level-12 basins it covers, and
// what is published for them, taken away as a table. The site is static, so the
// selection runs here in the browser against the display geometry the map already
// draws. That geometry is simplified, so membership near an edge can differ from
// an exact GIS overlay by a basin; the export says so.

export const AOI_RULES = [
  { id: 'intersects', label: 'Touches the area', note: 'any overlap, however small' },
  { id: 'centroid', label: 'Centre inside', note: 'basin centre falls inside the area' },
  { id: 'within', label: 'Entirely inside', note: 'the whole basin is inside the area' },
];

// Per-basin files are fetched one by one from a static host. A country-sized
// polygon would ask for thousands; the cap keeps a download bounded and honest.
export const AOI_FETCH_CAP = 1000;

const EARTH_RADIUS_KM = 6371.0088;

/** Close a ring of [lng, lat] vertices, dropping a repeated last vertex first. */
export function closeRing(vertices) {
  const ring = vertices.map(([lng, lat]) => [Number(lng), Number(lat)]);
  if (ring.length > 1) {
    const [a, b] = [ring[0], ring[ring.length - 1]];
    if (a[0] === b[0] && a[1] === b[1]) ring.pop();
  }
  return ring.length >= 3 ? [...ring, ring[0]] : ring;
}

export function aoiFeature(vertices) {
  return {
    type: 'Feature',
    properties: { name: 'Area of interest', crs: 'EPSG:4326' },
    geometry: { type: 'Polygon', coordinates: [closeRing(vertices)] },
  };
}

function bboxOfRings(rings) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const ring of rings) {
    for (const [x, y] of ring) {
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
    }
  }
  return [minX, minY, maxX, maxY];
}

const bboxesTouch = (a, b) => a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3];

/** Ray casting; a point exactly on an edge may land either way, which is fine here. */
export function ringContains(ring, [x, y]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Polygon rings [outer, ...holes]: inside the outer ring and in no hole. */
export function polygonContains(rings, point) {
  if (!rings.length || !ringContains(rings[0], point)) return false;
  return !rings.slice(1).some(hole => ringContains(hole, point));
}

function orientation(a, b, c) {
  const value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1]);
  return value > 0 ? 1 : value < 0 ? -1 : 0;
}

function onSegment(a, b, p) {
  return Math.min(a[0], b[0]) <= p[0] && p[0] <= Math.max(a[0], b[0])
    && Math.min(a[1], b[1]) <= p[1] && p[1] <= Math.max(a[1], b[1]);
}

export function segmentsCross(a, b, c, d) {
  const o1 = orientation(a, b, c); const o2 = orientation(a, b, d);
  const o3 = orientation(c, d, a); const o4 = orientation(c, d, b);
  if (o1 !== o2 && o3 !== o4) return true;
  return (o1 === 0 && onSegment(a, b, c)) || (o2 === 0 && onSegment(a, b, d))
    || (o3 === 0 && onSegment(c, d, a)) || (o4 === 0 && onSegment(c, d, b));
}

function ringsCross(ringA, ringB) {
  for (let i = 1; i < ringA.length; i += 1) {
    for (let j = 1; j < ringB.length; j += 1) {
      if (segmentsCross(ringA[i - 1], ringA[i], ringB[j - 1], ringB[j])) return true;
    }
  }
  return false;
}

/** A GeoJSON Polygon or MultiPolygon as a list of polygons, each a list of rings. */
export function polygonsOf(geometry) {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return [geometry.coordinates];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates;
  return [];
}

// Planar area-weighted centroid of the largest part, in degrees. Good enough to
// decide which side of a hand-drawn line a basin's centre falls on.
export function centroidOf(geometry) {
  let best = null;
  for (const rings of polygonsOf(geometry)) {
    const ring = rings[0];
    let area = 0; let cx = 0; let cy = 0;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
      const cross = ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
      area += cross;
      cx += (ring[j][0] + ring[i][0]) * cross;
      cy += (ring[j][1] + ring[i][1]) * cross;
    }
    if (!area) continue;
    const candidate = { area: Math.abs(area), point: [cx / (3 * area), cy / (3 * area)] };
    if (!best || candidate.area > best.area) best = candidate;
  }
  return best?.point || null;
}

/** Whether a basin geometry meets the area under one of the AOI_RULES. */
export function basinMatches(geometry, aoiRing, rule = 'intersects', aoiBox = bboxOfRings([aoiRing])) {
  const polygons = polygonsOf(geometry);
  if (!polygons.length || aoiRing.length < 4) return false;
  if (!bboxesTouch(bboxOfRings(polygons.map(rings => rings[0])), aoiBox)) return false;
  const aoi = [aoiRing];
  if (rule === 'centroid') {
    const centre = centroidOf(geometry);
    return Boolean(centre) && polygonContains(aoi, centre);
  }
  const edgesCross = polygons.some(rings => rings.some(ring => ringsCross(ring, aoiRing)));
  if (rule === 'within') {
    return !edgesCross && polygons.every(rings => polygonContains(aoi, rings[0][0]));
  }
  if (edgesCross) return true;
  // No edges cross, so one shape holds the other entirely, or they are apart.
  return polygons.some(rings => polygonContains(aoi, rings[0][0]))
    || polygons.some(rings => polygonContains(rings, aoiRing[0]));
}

/** Level-12 basins meeting the area, sorted by id, with what the map already knows. */
export function selectBasins(features, vertices, rule = 'intersects') {
  const ring = closeRing(vertices);
  if (ring.length < 4) return [];
  const box = bboxOfRings([ring]);
  return (features || [])
    .filter(feature => basinMatches(feature.geometry, ring, rule, box))
    .map(feature => ({
      hybas_id: String(feature.properties.hybas_id),
      system_id: feature.properties.system_id || '',
      area_km2: feature.properties.area_km2 ?? null,
      upstream_km2: feature.properties.upstream_km2 ?? null,
      feature,
    }))
    .sort((a, b) => a.hybas_id.localeCompare(b.hybas_id));
}

/** Geodesic area of the drawn ring in km², for the reader's orientation only. */
export function ringAreaKm2(vertices) {
  const ring = closeRing(vertices);
  if (ring.length < 4) return 0;
  const rad = Math.PI / 180;
  let total = 0;
  for (let i = 1; i < ring.length; i += 1) {
    const [lng1, lat1] = ring[i - 1];
    const [lng2, lat2] = ring[i];
    total += (lng2 - lng1) * rad * (2 + Math.sin(lat1 * rad) + Math.sin(lat2 * rad));
  }
  return Math.abs((total * EARTH_RADIUS_KM * EARTH_RADIUS_KM) / 2);
}

export function summarise(basins) {
  const bySystem = {};
  let area = 0;
  for (const basin of basins) {
    bySystem[basin.system_id] = (bySystem[basin.system_id] || 0) + 1;
    area += Number(basin.area_km2) || 0;
  }
  return { count: basins.length, areaKm2: area, bySystem };
}

// ------------------------------------------------------------------ tables

export function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = typeof value === 'number' ? (Number.isFinite(value) ? String(value) : '') : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(header, rows) {
  return `${[header, ...rows].map(row => row.map(csvCell).join(',')).join('\n')}\n`;
}

export function basinListCsv(basins) {
  return toCsv(['hybas_id', 'system_id', 'area_km2', 'upstream_km2'],
    basins.map(basin => [basin.hybas_id, basin.system_id, basin.area_km2, basin.upstream_km2]));
}

// One row per basin; every attribute twice, the published value and this project's
// estimate side by side, so the two are never mistaken for one another.
export function attributesCsv(catalogue, records) {
  const columns = catalogue.attributes;
  const header = ['hybas_id', 'system_id', 'area_km2',
    ...columns.flatMap(column => [`${column}_hydroatlas`, `${column}_estimate`])];
  const rows = records.map(record => [
    record.basin_id, record.system, record.area_km2,
    ...columns.flatMap((_, index) => [record.original?.[index] ?? null, record.substitute?.[index] ?? null]),
  ]);
  return toCsv(header, rows);
}

// BasinATLAS spatial support: this sub-basin, everything upstream, or the pour point.
const SUPPORT = { s: 'sub-basin', u: 'upstream', p: 'pour point' };

export function dictionaryCsv(catalogue) {
  const header = ['column', 'label', 'category', 'support', 'hydroatlas_unit', 'hydroatlas_dataset',
    'estimate_unit', 'estimate_statistic', 'estimate_period_start', 'estimate_period_end',
    'estimate_source_release', 'estimate_method'];
  const rows = catalogue.attributes.map(column => {
    const meta = catalogue.meta?.[column] || {};
    const estimate = meta.substitute || {};
    const period = Array.isArray(estimate.period) ? estimate.period : [];
    return [column, meta.label, meta.category, SUPPORT[meta.support] || meta.support,
      meta.unit, meta.original?.dataset, estimate.unit, estimate.statistic, period[0], period[1],
      estimate.source_release, estimate.method];
  });
  return toCsv(header, rows);
}

// Long form: one row per basin, series and month. A missing month stays empty.
export function historyCsv(histories) {
  const header = ['hybas_id', 'series', 'unit', 'year', 'month', 'value'];
  const rows = [];
  for (const history of histories) {
    const start = history.years[0];
    for (const name of Object.keys(history.series || {}).sort()) {
      const series = history.series[name];
      series.values.forEach((value, position) => {
        rows.push([history.basin_id, name, series.unit, start + Math.floor(position / 12), (position % 12) + 1, value]);
      });
    }
  }
  return toCsv(header, rows);
}

export function exportDocument({ vertices, rule, basins, catalogue, records, histories, release, generatedAt }) {
  const byId = new Map((records || []).map(record => [String(record.basin_id), record]));
  const historyById = new Map((histories || []).map(history => [String(history.basin_id), history]));
  return {
    type: 'uzgeodata.area_of_interest',
    generated_at: generatedAt,
    release: release || null,
    area_of_interest: aoiFeature(vertices),
    area_of_interest_km2: ringAreaKm2(vertices),
    selection: {
      rule,
      basin_level: 12,
      geometry: 'Display geometry (simplified); membership at the edge may differ from an exact overlay.',
      count: basins.length,
    },
    reading: catalogue?.reading || null,
    attribute_columns: catalogue?.attributes || [],
    attribute_meta: catalogue?.meta || null,
    basins: basins.map(basin => {
      const record = byId.get(basin.hybas_id);
      const history = historyById.get(basin.hybas_id);
      return {
        hybas_id: basin.hybas_id,
        system_id: basin.system_id,
        area_km2: basin.area_km2,
        upstream_km2: basin.upstream_km2,
        ...(record ? { hydroatlas: record.original, estimate: record.substitute } : {}),
        ...(history ? { monthly: { years: history.years, series: history.series } } : {}),
      };
    }),
    note: 'hydroatlas and estimate arrays are positional against attribute_columns. Estimates are independent '
      + 'open-data values, not reproductions. Upstream (support "u") values must not be summed across basins.',
  };
}

/** Fetch many JSON documents with bounded concurrency, collecting failures instead of stopping. */
export async function fetchAll(urls, { concurrency = 8, fetcher = fetch, onProgress = () => {} } = {}) {
  const results = new Array(urls.length);
  const failures = [];
  let next = 0; let done = 0;
  const worker = async () => {
    while (next < urls.length) {
      const index = next; next += 1;
      try {
        const response = await fetcher(urls[index]);
        const type = response.headers?.get?.('content-type') || 'application/json';
        if (!response.ok || !type.includes('json')) throw Error(`${response.status}`);
        results[index] = await response.json();
      } catch (error) {
        failures.push({ url: urls[index], reason: error.message });
      }
      done += 1;
      onProgress(done, urls.length);
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, urls.length) }, worker));
  return { results, failures };
}
