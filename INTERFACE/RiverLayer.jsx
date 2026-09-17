import React, { useMemo } from 'react';
import { GeoJSON, Pane, useMap, useMapEvents } from 'react-leaflet';
import { svg } from 'leaflet';
import { withinBounds } from './landingModel.js';

/**
 * SWOT-observed river reaches: real satellite-radar readings of level and
 * width along the wide rivers of the basin (Syr Darya, Panj, Amu Darya,
 * Vakhsh, Naryn and the rest), distinct from the static background
 * hydrography line already drawn under it. A reach that has at least a few
 * quality-passing overpasses is drawn solid and clickable; a named reach
 * SWOT has not yet returned usable data for is drawn faint, so the network
 * reads as complete without implying every strand has a chart behind it.
 */
function useView() {
  const map = useMap();
  const read = () => {
    const bounds = map.getBounds().pad(0.25);
    return [[bounds.getSouth(), bounds.getWest()], [bounds.getNorth(), bounds.getEast()]];
  };
  const [bounds, setBounds] = React.useState(read);
  useMapEvents({ moveend: () => setBounds(read()), zoomend: () => setBounds(read()) });
  return bounds;
}

export default function RiverLayer({ data, onSelect }) {
  const bounds = useView();
  const renderer = useMemo(() => svg({ pane: 'riverReachPane' }), []);

  const visible = useMemo(() => {
    if (!data) return null;
    const features = data.features.filter(feature => {
      const coords = feature.geometry?.coordinates || [];
      const mid = coords[Math.floor(coords.length / 2)];
      return withinBounds(mid, bounds);
    });
    return { ...data, features };
  }, [data, bounds]);

  if (!visible) return null;

  return <Pane name="riverReachPane" style={{ zIndex: 440 }}>
    <GeoJSON key={`reaches-${visible.features.length}`} data={visible} renderer={renderer}
      style={feature => ({
        color: '#3fd0ff',
        weight: feature.properties.has_chart ? 3 : 1.6,
        opacity: feature.properties.has_chart ? 0.85 : 0.35,
        dashArray: feature.properties.has_chart ? null : '1 4',
      })}
      onEachFeature={(feature, layer) => {
        const { river_group: river, basin, n_good_or_suspect: n } = feature.properties;
        layer.bindTooltip(`${river} (${basin})${n ? ` · ${n} SWOT passes` : ' · no SWOT data yet'}`, { sticky: true });
        if (feature.properties.has_chart) layer.on('click', () => onSelect(feature.properties));
      }} />
  </Pane>;
}
