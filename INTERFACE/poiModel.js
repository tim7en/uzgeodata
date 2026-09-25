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

export function reportMembers(index, basins) {
  const positions = new Map(index.ids.map((id, i) => [String(id), i]));
  const roots = [...new Set(basins.map(f => String(f.properties.hybas_id)))];
  if (!roots.length || roots.some(id => !positions.has(id))) throw Error('Some matched basins have no published statistics. No partial report was generated.');
  const network = buildUpstreamMap(index.ids.map((id, i) => ({ id: String(id), nextDown: String(index.next_down[i] || '') })));
  const upstream = [...traceUpstreamFrom(roots, network).ids].map(id => positions.get(id)).filter(i => i !== undefined);
  return { local: roots.map(id => positions.get(id)), upstream };
}

export const REPORT_METHOD = 'Local: full matched level-12 sub-basins. Upstream: their union plus all connected upstream sub-basins, counted once, including virtual links. Monthly means use local basin area as weights. Full-area means and totals are withheld if any member lacks data. This is basin assignment, not river snapping or catchment delineation at the uploaded coordinate. Polygon results describe whole intersecting basins, not a clipped polygon. Matching uses simplified map outlines; boundary matches can differ from a full-resolution GIS overlay.';

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
    local: { ids: ids('local'), ...aggregateCatchment(index, values, members.local, variable) },
    upstream: { ids: ids('upstream'), ...aggregateCatchment(index, values, members.upstream, variable) },
    morphology: match.basins.length === 1 ? morphology?.basins?.[ids('local')[0]] || null : null,
    morphology_notes: morphology?.notes || [],
    local_geometry: collection(match.basins), upstream_geometry: upstreamGeometry,
    geometry_missing_ids: ids('upstream').filter(id => !geometryIds.has(id)),
  };
}

export function reportMonthlyCsv(report) {
  const columns = Object.keys(report.local.rows[0]);
  return toCsv(['scope', 'variable', 'unit', 'total_unit', ...columns], ['local', 'upstream'].flatMap(scope =>
    report[scope].rows.map(row => [scope, report.variable, report.meta.unit, report[scope].total.unit, ...columns.map(key => row[key])])));
}
