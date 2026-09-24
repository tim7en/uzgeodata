import { buildUpstreamMap, traceUpstream } from './basinTrace.js';
import { collectionBounds } from './mapViewModel.js';

// Trace only the selected resolution. IDs must never be joined across levels.
export function basinCatchment(collection, basin) {
  const level = Number(basin.basin_level);
  const features = (collection?.features || []).filter(feature =>
    Number(feature.properties.basin_level) === level);
  const selected = features.find(feature => String(feature.properties.hybas_id) === String(basin.hybas_id));
  if (!selected) return null;
  const network = buildUpstreamMap(features.map(({ properties: p }) => ({
    id: String(p.hybas_id), nextDown: p.next_down ? String(p.next_down) : null,
  })));
  const { ids } = traceUpstream(String(basin.hybas_id), network);
  const members = features.filter(feature => ids.has(String(feature.properties.hybas_id)));
  const upstream = members.filter(feature => feature !== selected);
  const areaKm2 = members.reduce((area, feature) => area + (Number(feature.properties.area_km2) || 0), 0);
  return {
    selected, upstream: { type: 'FeatureCollection', features: upstream },
    count: upstream.length, areaKm2, bounds: collectionBounds(members),
    selectedBounds: collectionBounds([selected]),
    partial: Number(basin.upstream_km2) > 0 && areaKm2 < Number(basin.upstream_km2) * 0.95,
  };
}
