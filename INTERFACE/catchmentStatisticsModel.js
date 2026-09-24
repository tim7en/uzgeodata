import { buildUpstreamMap, traceUpstream } from './basinTrace.js';
import { toCsv } from './aoiModel.js';

const WATER_DEPTHS = new Set(['pre_mm_s', 'run_mm_s', 'aet_mm_s', 'pet_mm_s', 'soil_mm_s']);

export function catchmentMembers(index, basinId) {
  const root = String(basinId);
  const positions = new Map(index.ids.map((id, position) => [String(id), position]));
  if (!positions.has(root)) throw Error('This basin is not in the published level-12 statistics package.');
  const network = buildUpstreamMap(index.ids.map((id, i) => ({ id: String(id), nextDown: index.next_down[i] ? String(index.next_down[i]) : null })));
  return [...traceUpstream(root, network).ids].map(id => positions.get(id)).filter(i => i !== undefined);
}

export function decodeMatrix(bytes, index) {
  const size = index.ids.length * index.months;
  if (index.encoding !== 'gzip-byte-shuffled-delta-int32-le-basin-major' || bytes.length !== size * 4) {
    throw Error('The monthly statistics package has an invalid encoding or size.');
  }
  const values = new Int32Array(size);
  for (let i = 0; i < size; i++) {
    values[i] = bytes[i] | (bytes[size + i] << 8) | (bytes[2 * size + i] << 16) | (bytes[3 * size + i] << 24);
    if (i % index.months !== 0) values[i] = (values[i] + values[i - 1]) | 0;
  }
  return values;
}

export function totalDefinition(name, unit) {
  if (WATER_DEPTHS.has(name) && /^millimetres(?: per month)?$/.test(unit)) {
    return { unit: 'm³', label: 'Water volume', factor: 1000,
      note: 'Sum of depth (mm) × local sub-basin area (km²) × 1,000; runoff volume is generated runoff, not routed outlet discharge.' };
  }
  if (name === 'snw_pc_s' && /percent/.test(unit)) {
    return { unit: 'km²', label: 'Snow-covered area', factor: 0.01,
      note: 'Sum of snow-cover percentage × local sub-basin area / 100; no trend interpretation.' };
  }
  return { unit: null, label: 'Total not applicable', factor: null,
    note: 'These values are intensive: adding temperatures or incompatible quantities has no physical meaning.' };
}

export function aggregateCatchment(index, values, members, name) {
  if (!members.length || values.length !== index.ids.length * index.months) throw Error('Invalid catchment matrix.');
  const totalArea = members.reduce((sum, position) => sum + index.areas_km2[position], 0);
  if (!(totalArea > 0)) throw Error('Catchment area is unavailable.');
  const definition = totalDefinition(name, index.series[name].meta.unit);
  const rows = [];
  for (let month = 0; month < index.months; month++) {
    let weighted = 0, observedArea = 0, count = 0, min = Infinity, max = -Infinity;
    for (const position of members) {
      const encoded = values[position * index.months + month];
      if (encoded === index.null_sentinel) continue;
      const value = encoded / index.scale, area = index.areas_km2[position];
      if (!(area > 0) || !Number.isFinite(value)) throw Error('Invalid monthly value or basin area.');
      weighted += value * area; observedArea += area; count++;
      min = Math.min(min, value); max = Math.max(max, value);
    }
    const complete = count === members.length;
    rows.push({
      year: index.years[0] + Math.floor(month / 12), month: month % 12 + 1,
      mean_observed_area: count ? weighted / observedArea : null,
      mean_full_catchment: complete ? weighted / totalArea : null,
      min_subbasin_value: count ? min : null, max_subbasin_value: count ? max : null,
      total_full_catchment: complete && definition.factor !== null ? weighted * definition.factor : null,
      total_observed_area: count && definition.factor !== null ? weighted * definition.factor : null,
      observed_basins: count, basin_count: members.length, observed_area_km2: observedArea,
      catchment_area_km2: totalArea, area_coverage_percent: 100 * observedArea / totalArea,
    });
  }
  return { rows, total: definition, areaKm2: totalArea };
}

export function statisticsCsv(basinId, name, meta, result) {
  const columns = Object.keys(result.rows[0]);
  return toCsv(['outlet_hybas_id', 'variable', 'value_unit', 'total_unit', ...columns],
    result.rows.map(row => [basinId, name, meta.unit, result.total.unit, ...columns.map(column => row[column])]));
}

export const MORPHOLOGY_FIELDS = [
  ['traced_area_km2', 'Sum of local basin areas', 'km²'],
  ['reported_upstream_area_km2', 'Reported upstream area', 'km²'],
  ['geometry_area_km2', 'Dissolved boundary area', 'km²'],
  ['outer_perimeter_km', 'Outer perimeter', 'km'],
  ['boundary_span_km', 'Basin length (boundary span)', 'km'],
  ['upstream_outlet_path_km', 'Longest upstream outlet path', 'km'],
  ['highest_elevation_m', 'Highest elevation', 'm a.s.l.'],
  ['lowest_elevation_m', 'Lowest elevation', 'm a.s.l.'],
  ['mean_elevation_m', 'Area-weighted mean elevation', 'm a.s.l.'],
  ['relief_m', 'Relief', 'm'], ['mean_slope_deg', 'Area-weighted mean slope', 'degrees'],
  ['circularity', 'Circularity ratio', ''], ['elongation_ratio', 'Elongation ratio (boundary span)', ''],
  ['hypsometric_integral', 'Hypsometric integral (approximate)', ''],
];
