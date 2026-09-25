import { polygonContains, polygonsOf, segmentsCross, toCsv } from './aoiModel.js';
import { buildUpstreamMap, traceUpstreamFrom } from './basinTrace.js';
import { aggregateCatchment } from './catchmentStatisticsModel.js';

export const MAX_POIS = 100;
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
const collection = features => ({ type: 'FeatureCollection', features });

function csvRows(text) {
  const rows = []; let row = [], cell = '', quoted = false;
  for (let i = 0; i <= text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted;
    } else if (!quoted && (c === ',' || c === '\n' || c === undefined)) {
      row.push(cell.replace(/\r$/, '')); cell = '';
      if (c !== ',') { if (row.some(value => value.trim())) rows.push(row); row = []; }
    } else cell += c;
  }
  if (quoted) throw Error('CSV has an unclosed quoted field.');
  return rows;
}

export function parsePois(text, filename = '') {
  text = text.replace(/^\uFEFF/, '');
  let data;
  if (/\.csv$/i.test(filename)) {
    const [header, ...rows] = csvRows(text);
    const keys = (header || []).map(value => value.trim().toLowerCase());
    const lon = keys.findIndex(key => ['longitude', 'lon', 'lng'].includes(key));
    const lat = keys.findIndex(key => ['latitude', 'lat'].includes(key));
    if (lon < 0 || lat < 0) throw Error('CSV needs longitude and latitude columns in decimal degrees.');
    data = collection(rows.map((row, i) => {
      if (row.length !== keys.length || !row[lon].trim() || !row[lat].trim()) throw Error(`CSV row ${i + 2} has missing fields.`);
      return { type: 'Feature', properties: Object.fromEntries(keys.map((key, j) => [key, row[j]])),
        geometry: { type: 'Point', coordinates: [Number(row[lon]), Number(row[lat])] } };
    }));
  } else {
    try { data = JSON.parse(text); } catch { throw Error('Upload valid GeoJSON or a CSV with longitude and latitude columns.'); }
  }
  const crs = data?.crs?.properties?.name;
  if (crs && !/4326|CRS84/i.test(crs)) throw Error('Reproject the file to WGS84 (EPSG:4326) before uploading.');
  const features = data?.type === 'FeatureCollection' ? data.features : data?.type === 'Feature' ? [data]
    : data?.coordinates ? [{ type: 'Feature', properties: {}, geometry: data }] : [];
  if (!Array.isArray(features) || !features.length || features.length > MAX_POIS) throw Error(`Upload 1–${MAX_POIS} features.`);
  let vertices = 0;
  const coordinate = point => {
    vertices++;
    if (!Array.isArray(point) || point.length < 2 || !point.slice(0, 2).every(Number.isFinite)
      || Math.abs(point[0]) > 180 || Math.abs(point[1]) > 90) throw Error('Coordinates must be WGS84 longitude, latitude in decimal degrees.');
    if (vertices > 50000) throw Error('The file exceeds 50,000 vertices. Simplify the polygons before uploading.');
  };
  return collection(features.map((feature, i) => {
    const geometry = feature.geometry;
    if (feature.type !== 'Feature' || !['Point', 'Polygon', 'MultiPolygon'].includes(geometry?.type)) {
      throw Error(`Feature ${i + 1}: only Point, Polygon and MultiPolygon are supported.`);
    }
    if (geometry.type === 'Point') coordinate(geometry.coordinates);
    else {
      const polygons = polygonsOf(geometry);
      if (!Array.isArray(polygons) || !polygons.length) throw Error(`Feature ${i + 1}: empty polygon.`);
      for (const rings of polygons) {
        if (!Array.isArray(rings) || !rings.length) throw Error(`Feature ${i + 1}: empty polygon.`);
        for (const ring of rings) {
          if (!Array.isArray(ring) || ring.length < 4) throw Error(`Feature ${i + 1}: a polygon ring needs at least four coordinates.`);
          ring.forEach(coordinate);
          if (ring[0][0] !== ring.at(-1)[0] || ring[0][1] !== ring.at(-1)[1]) throw Error(`Feature ${i + 1}: polygon rings must be closed.`);
          let area = 0;
          for (let j = 1; j < ring.length; j++) area += ring[j - 1][0] * ring[j][1] - ring[j][0] * ring[j - 1][1];
          if (Math.abs(area) < 1e-12) throw Error(`Feature ${i + 1}: polygon ring has no area or is invalid.`);
        }
      }
    }
    const properties = feature.properties && typeof feature.properties === 'object' ? feature.properties : {};
    const name = String(properties.name || properties.Name || properties.id || feature.id || `Location ${i + 1}`).slice(0, 160);
    return { ...feature, properties: { ...properties, poi_name: name }, id: i + 1 };
  }));
}

const box = geometry => {
  const points = polygonsOf(geometry).flat(2);
  return points.reduce((b, [x, y]) => [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)], [Infinity, Infinity, -Infinity, -Infinity]);
};
const touches = (a, b) => a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3];
function polygonIntersects(a, b) {
  if (!touches(box(a), box(b))) return false;
  return polygonsOf(a).some(left => polygonsOf(b).some(right => {
    for (const lr of left) for (const rr of right) {
      for (let i = 1; i < lr.length; i++) for (let j = 1; j < rr.length; j++) {
        if (segmentsCross(lr[i - 1], lr[i], rr[j - 1], rr[j])) return true;
      }
    }
    return polygonContains(left, right[0][0]) || polygonContains(right, left[0][0]);
  }));
}

// Local equirectangular distance to the boundary, used only within the explicit
// short snap tolerance. This assigns a basin; it does not delineate a new outlet.
function nearestBoundary(point, geometry) {
  const sx = 111.195 * Math.cos(point[1] * Math.PI / 180), sy = 111.195;
  let best = { distanceKm: Infinity, coordinate: null };
  for (const rings of polygonsOf(geometry)) for (const ring of rings) for (let i = 1; i < ring.length; i++) {
    const a = ring[i - 1], b = ring[i];
    const ax = (a[0] - point[0]) * sx, ay = (a[1] - point[1]) * sy;
    const dx = (b[0] - a[0]) * sx, dy = (b[1] - a[1]) * sy;
    const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy || 1)));
    const distanceKm = Math.hypot(ax + t * dx, ay + t * dy);
    if (distanceKm < best.distanceKm) best = { distanceKm, coordinate: [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])] };
  }
  return best;
}

export function matchPoi(feature, basins, toleranceKm = 1) {
  if (!Number.isFinite(toleranceKm) || toleranceKm < 0 || toleranceKm > 10) throw Error('Snap distance must be between 0 and 10 km.');
  const candidates = basins.filter(f => Number(f.properties.basin_level) === 12)
    .slice().sort((a, b) => String(a.properties.hybas_id).localeCompare(String(b.properties.hybas_id)));
  if (feature.geometry.type !== 'Point') {
    const matches = candidates.filter(basin => polygonIntersects(feature.geometry, basin.geometry));
    return { status: matches.length ? 'intersects' : 'unmatched', basins: matches, distanceKm: null, coordinate: null };
  }
  const point = feature.geometry.coordinates;
  const inside = candidates.filter(basin => polygonsOf(basin.geometry).some(rings => polygonContains(rings, point)));
  if (inside.length) return { status: 'contained', basins: [inside[0]], distanceKm: 0, coordinate: point, candidateCount: inside.length };
  let nearest = null;
  for (const basin of candidates) {
    const bounds = box(basin.geometry);
    const dx = Math.max(bounds[0] - point[0], 0, point[0] - bounds[2]) * 111.195 * Math.cos(point[1] * Math.PI / 180);
    const dy = Math.max(bounds[1] - point[1], 0, point[1] - bounds[3]) * 111.195;
    if (nearest && Math.hypot(dx, dy) > nearest.distanceKm) continue;
    const distance = nearestBoundary(point, basin.geometry);
    if (!nearest || distance.distanceKm < nearest.distanceKm) nearest = { ...distance, basin };
  }
  const accepted = nearest && nearest.distanceKm <= toleranceKm + 1e-8;
  return { status: accepted ? 'snapped' : 'unmatched', basins: accepted ? [nearest.basin] : [],
    distanceKm: nearest?.distanceKm ?? null, coordinate: accepted ? nearest.coordinate : null };
}

/**
 * The level-12 units a basin selected on the map is made of.
 *
 * The map draws level 7 at a regional view and level 12 only close in, so a reader
 * who clicks a basin usually clicks a coarse one. Statistics are published for
 * level 12, which is why the report was simply unavailable there. A coarse basin
 * is not a different thing, though: Pfafstetter ids nest by prefix, so its units
 * are every level-12 basin whose id begins with its own, and the report about it
 * is the report about them.
 *
 * Nothing is matched geometrically here. The containing basin is known from the
 * identifier, and asking a polygon matcher instead would return every neighbour
 * that shares a boundary with it.
 */
export function basinUnits(features, basin) {
  const units = features.filter(item => Number(item.properties.basin_level) === 12);
  if (Number(basin?.basin_level) === 12) {
    return units.filter(item => String(item.properties.hybas_id) === String(basin.hybas_id));
  }
  const prefix = String(basin?.pfaf_id ?? '');
  if (!prefix) return [];
  return units.filter(item => String(item.properties.pfaf_id).startsWith(prefix));
}

export function reportMembers(index, basins) {
  const positions = new Map(index.ids.map((id, i) => [String(id), i]));
  const roots = [...new Set(basins.map(f => String(f.properties.hybas_id)))];
  if (!roots.length || roots.some(id => !positions.has(id))) throw Error('Some matched basins have no published statistics. No partial report was generated.');
  const network = buildUpstreamMap(index.ids.map((id, i) => ({ id: String(id), nextDown: String(index.next_down[i] || '') })));
  const upstream = [...traceUpstreamFrom(roots, network).ids].map(id => positions.get(id)).filter(i => i !== undefined);
  return { local: roots.map(id => positions.get(id)), upstream };
}

// A monthly value on its own says nothing: 40 mm of rain is a drought in April and
// a deluge in September. These turn the rows a report already carries into the two
// comparisons a reader is actually making - this month against the same month in
// the record, and the record against itself over time.

/** Complete calendar years, which is what a normal and an annual trend need. */
function completeYears(rows) {
  const byYear = new Map();
  for (const row of rows) {
    if (!(row.observed_basins > 0) || row.mean_observed_area === null) continue;
    const year = byYear.get(row.year) || [];
    year.push(row);
    byYear.set(row.year, year);
  }
  return [...byYear.entries()].filter(([, months]) => months.length === 12).sort((a, b) => a[0] - b[0]);
}

/**
 * The mean for each calendar month over the complete years of the record.
 *
 * Not a 1991-2020 normal: this record starts in 2003, and calling a 2003-2024 mean
 * a climate normal would borrow authority the period does not have. It is stated
 * as what it is - the baseline available here - with its years attached so a
 * reader can judge it.
 */
export function monthlyNormals(rows) {
  const years = completeYears(rows);
  if (years.length < 10) return null;
  const sums = Array.from({ length: 12 }, () => []);
  for (const [, months] of years) for (const row of months) sums[row.month - 1].push(row.mean_observed_area);
  return {
    firstYear: years[0][0],
    lastYear: years.at(-1)[0],
    years: years.length,
    byMonth: sums.map(values => values.reduce((total, value) => total + value, 0) / values.length),
    samples: sums,
  };
}

function mannKendall(values) {
  let score = 0;
  for (let i = 0; i < values.length - 1; i += 1) {
    for (let j = i + 1; j < values.length; j += 1) score += Math.sign(values[j] - values[i]);
  }
  const ties = new Map();
  for (const value of values) ties.set(value, (ties.get(value) || 0) + 1);
  let variance = values.length * (values.length - 1) * (2 * values.length + 5);
  for (const count of ties.values()) variance -= count * (count - 1) * (2 * count + 5);
  variance /= 18;
  const z = score === 0 || variance <= 0 ? 0
    : (score > 0 ? score - 1 : score + 1) / Math.sqrt(variance);
  // Two-sided p from the normal approximation, which is what Mann-Kendall uses
  // once a series is longer than about ten points.
  const p = 2 * (1 - 0.5 * (1 + erf(Math.abs(z) / Math.SQRT2)));
  return { score, z, p };
}

function erf(x) {
  // Abramowitz and Stegun 7.1.26: enough for a reported significance, and it keeps
  // this file free of a statistics dependency.
  const t = 1 / (1 + 0.3275911 * x);
  const y = 1 - ((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t * t
    * Math.exp(-x * x) - 0.254829592 * t * Math.exp(-x * x);
  return Math.max(0, Math.min(1, y));
}

function senSlope(points) {
  const slopes = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const run = points[j][0] - points[i][0];
      if (run !== 0) slopes.push((points[j][1] - points[i][1]) / run);
    }
  }
  if (!slopes.length) return null;
  slopes.sort((left, right) => left - right);
  const middle = slopes.length >> 1;
  return slopes.length % 2 ? slopes[middle] : (slopes[middle - 1] + slopes[middle]) / 2;
}

/**
 * The annual series and its trend.
 *
 * Extensive quantities are summed over the year and intensive ones averaged,
 * decided by whether the package defines a total for the variable rather than by
 * guessing from the unit. Only complete years are used: a year missing four months
 * is not a low year.
 */
export function annualSeries(rows, total) {
  const years = completeYears(rows);
  const extensive = total?.factor !== null && total?.factor !== undefined;
  const series = years.map(([year, months]) => {
    const values = months.map(row => row.mean_observed_area);
    const sum = values.reduce((carried, value) => carried + value, 0);
    return { year, value: extensive ? sum : sum / values.length };
  });
  if (series.length < 10) return { series, extensive, trend: null };
  const { score, z, p } = mannKendall(series.map(entry => entry.value));
  const slope = senSlope(series.map(entry => [entry.year, entry.value]));
  return {
    series,
    extensive,
    trend: {
      years: series.length, score, z, p,
      slopePerYear: slope,
      slopePerDecade: slope === null ? null : slope * 10,
      significant: p < 0.05,
      direction: slope === null || p >= 0.05 ? 'no detectable trend' : slope > 0 ? 'increasing' : 'decreasing',
    },
  };
}

/**
 * Where the most recent months sit against the baseline.
 *
 * Percent anomalies are reported only where zero means none of the quantity -
 * rainfall, runoff, snow-covered area. A temperature anomaly in percent would be a
 * statement about the Celsius scale rather than about the weather.
 */
export function currentConditions(rows, total) {
  const normals = monthlyNormals(rows);
  const observed = rows.filter(row => row.observed_basins > 0 && row.mean_observed_area !== null);
  if (!observed.length) return null;
  const latest = observed.at(-1);
  const ratioMeaningful = total?.factor !== null && total?.factor !== undefined;
  const normal = normals ? normals.byMonth[latest.month - 1] : null;
  const sample = normals ? normals.samples[latest.month - 1] : [];
  const below = sample.filter(value => value < latest.mean_observed_area).length;

  // Twelve months only when the twelve most recent positions were all observed:
  // a running total over a gap is a smaller number, not a drier year.
  const tail = observed.slice(-12);
  const contiguous = tail.length === 12 && tail.every((row, index) => index === 0
    || row.year * 12 + row.month === tail[index - 1].year * 12 + tail[index - 1].month + 1);
  const window = contiguous
    ? tail.reduce((carried, row) => carried + row.mean_observed_area, 0) / (ratioMeaningful ? 1 : 12)
    : null;
  const windowNormal = normals
    ? normals.byMonth.reduce((carried, value) => carried + value, 0) / (ratioMeaningful ? 1 : 12)
    : null;

  return {
    baseline: normals && { firstYear: normals.firstYear, lastYear: normals.lastYear, years: normals.years },
    latest: {
      year: latest.year, month: latest.month,
      value: latest.mean_observed_area,
      coveragePercent: latest.area_coverage_percent,
      normal,
      anomaly: normal === null ? null : latest.mean_observed_area - normal,
      anomalyPercent: normal && ratioMeaningful ? (latest.mean_observed_area - normal) / normal * 100 : null,
      rankPercentile: sample.length ? Math.round(100 * below / sample.length) : null,
      rankYears: sample.length,
    },
    lastTwelveMonths: window === null ? null : {
      value: window, normal: windowNormal,
      anomaly: windowNormal === null ? null : window - windowNormal,
      anomalyPercent: windowNormal && ratioMeaningful ? (window - windowNormal) / windowNormal * 100 : null,
      aggregation: ratioMeaningful ? 'sum' : 'mean',
    },
    ...annualSeries(rows, total),
  };
}

export const CONDITION_METHOD = 'Normals are the mean of each calendar month over the complete years '
  + 'of this record, not a 1991-2020 climate normal, and the years used are stated. Percent anomalies are '
  + 'given only where zero means none of the quantity. Annual figures use complete years only, so a year '
  + 'missing months is left out rather than counted low. The trend is Mann-Kendall with a Sen slope over '
  + 'those annual values; it describes this record and this catchment, and a variable whose record ends '
  + 'earlier is not extrapolated to the present.';

export const REPORT_METHOD = 'Local: full matched level-12 sub-basins. Upstream: their union plus all connected upstream sub-basins, counted once, including virtual links. Monthly means use local basin area as weights. Full-area means and totals are withheld if any member lacks data. This is basin assignment, not river snapping or catchment delineation at the uploaded coordinate. Polygon results describe whole intersecting basins, not a clipped polygon. Matching uses simplified map outlines; boundary matches can differ from a full-resolution GIS overlay.';

function withConditions(aggregate) {
  return { ...aggregate, conditions: currentConditions(aggregate.rows, aggregate.total) };
}

export function makePoiReport({ feature, match, index, values, variable, geometry, morphology, sourceFile, generatedAt = new Date().toISOString() }) {
  const members = reportMembers(index, match.basins);
  const entry = index.series[variable];
  const ids = scope => members[scope].map(i => String(index.ids[i]));
  const upstreamIds = new Set(ids('upstream'));
  const upstreamGeometry = collection(geometry.features.filter(f => upstreamIds.has(String(f.properties.hybas_id))));
  const geometryIds = new Set(upstreamGeometry.features.map(f => String(f.properties.hybas_id)));
  const provenance = [...new Set(members.upstream.map(i => entry.provenance_ids[i]))].map(i => entry.provenance[i]);
  return {
    version: 1, name: feature.properties.poi_name, sourceFile, generatedAt, input: feature,
    match: { status: match.status, distance_km: match.distanceKm, snapped_coordinate: match.coordinate, basin_ids: ids('local'), candidate_count: match.candidateCount || match.basins.length },
    method: REPORT_METHOD, variable, meta: entry.meta, provenance,
    source_hashes: { monthly: entry.sha256, history: index.history_sha256, geometry: index.display_geometry_sha256 },
    local: { ids: ids('local'), ...withConditions(aggregateCatchment(index, values, members.local, variable)) },
    upstream: { ids: ids('upstream'), ...withConditions(aggregateCatchment(index, values, members.upstream, variable)) },
    // Where this variable's record ends, taken from the package rather than from
    // the frame: every variable has 288 calendar positions and they do not all
    // reach the same month.
    coverage: entry.coverage || null,
    morphology: match.basins.length === 1 ? morphology?.basins?.[ids('local')[0]] || null : null,
    morphology_notes: morphology?.notes || [],
    local_geometry: collection(match.basins), upstream_geometry: upstreamGeometry,
    geometry_missing_ids: ids('upstream').filter(id => !geometryIds.has(id)),
  };
}

export function reportMonthlyCsv(report) {
  const columns = Object.keys(report.local.rows[0]);
  // `source` says whether a row is an observation or the estimate that continues
  // it past the end of its source. Without it a spreadsheet would show one
  // unbroken series and nothing to tell the two apart.
  return toCsv(['scope', 'variable', 'unit', 'total_unit', 'source', ...columns],
    ['local', 'upstream'].flatMap(scope => report[scope].rows.map(row => [
      scope, report.variable, report.meta.unit, report[scope].total.unit,
      row.observed_basins > 0 && row.mean_observed_area !== null ? 'observed' : 'no observation',
      ...columns.map(key => row[key]),
    ])));
}
