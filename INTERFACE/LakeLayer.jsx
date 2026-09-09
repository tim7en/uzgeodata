import React, { useCallback, useMemo, useState } from 'react';
import { GeoJSON, Marker, Pane, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import { divIcon, svg } from 'leaflet';
import {
  clusterLakes, formatNumber, labelledLakes, lakeClusterLabel, lakePosition,
  lakeSymbolSize, withinBounds,
} from './landingModel.js';

const { width: W, height: H } = lakeSymbolSize();

/**
 * The map symbol for a water body: the cartographic convention of parallel water
 * lines, drawn once at a fixed small size.
 *
 * It was previously 30x24 with a 5px halo, which at national zoom read as heavy
 * as the dam bubbles beside it — and a dam circle *means* something by its size
 * while a lake symbol only says "water is here". The halo stays, because the
 * symbol has to survive being drawn over a dark basin fill and a river, but it
 * is now proportional to a much smaller mark.
 */
const lines = (stroke, width) =>
  `<path d="M${W * .23} ${H * .27}h${W * .54}M${W * .08} ${H * .5}h${W * .84}M${W * .23} ${H * .73}h${W * .54}"`
  + ` fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round"/>`;

export const LAKE_SYMBOL =
  `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true">${lines('#0a1a24', 3)}${lines('#7fd4f2', 1.5)}</svg>`;

// A group carries the same water lines inside a ring, so it still reads as water
// rather than turning into a generic cluster bubble.
const groupSymbol = count =>
  `<svg viewBox="0 0 ${W + 8} ${H + 8}" aria-hidden="true">`
  + `<circle cx="${(W + 8) / 2}" cy="${(H + 8) / 2}" r="${(H + 6) / 2}" fill="#0a1a24" stroke="#7fd4f2" stroke-width="1.2" opacity="0.92"/>`
  + `<text x="${(W + 8) / 2}" y="${(H + 8) / 2 + 3.4}" text-anchor="middle"`
  + ` font-family="Barlow Condensed, sans-serif" font-size="9" font-weight="700" fill="#cbeeff">${count}</text>`
  + '</svg>';

const singleIcon = divIcon({
  className: 'land-lake-symbol', html: LAKE_SYMBOL,
  iconSize: [W, H], iconAnchor: [W / 2, H / 2],
});
const groupIcons = new Map();
const groupIcon = count => {
  if (!groupIcons.has(count)) {
    groupIcons.set(count, divIcon({
      className: 'land-lake-symbol land-lake-group', html: groupSymbol(count),
      iconSize: [W + 8, H + 8], iconAnchor: [(W + 8) / 2, (H + 8) / 2],
    }));
  }
  return groupIcons.get(count);
};

/** Track the map's view so symbols and names follow what is actually on screen. */
function useView() {
  const map = useMap();
  const read = () => ({ bounds: boxOf(map), zoom: map.getZoom() });
  const [view, setView] = useState(read);
  useMapEvents({ moveend: () => setView(read()), zoomend: () => setView(read()) });
  return view;
}

function boxOf(map) {
  const bounds = map.getBounds().pad(0.25);
  return [[bounds.getSouth(), bounds.getWest()], [bounds.getNorth(), bounds.getEast()]];
}

export default function LakeLayer({ data, onSelect }) {
  const { bounds, zoom } = useView();
  // A separate SVG pane keeps a full-map canvas off the basin hit surface.
  const renderer = useMemo(() => svg({ pane: 'lakePane' }), []);

  // Shorelines are the real geometry, so they are drawn for everything in view
  // rather than being replaced by the symbol. Culling to the viewport is what
  // keeps 1,393 polygons from all living in the DOM at close zoom.
  const shorelines = useMemo(() => {
    if (!data) return null;
    const features = data.features.filter(feature => withinBounds(lakePosition(feature), bounds));
    return { ...data, features };
  }, [data, bounds]);

  const clusters = useMemo(
    () => clusterLakes(shorelines?.features || [], zoom),
    [shorelines, zoom],
  );
  const named = useMemo(() => labelledLakes(clusters, zoom), [clusters, zoom]);

  const open = useCallback(cluster => {
    // A group opens its largest member: the one a reader was most likely aiming
    // at, and the one the label already named.
    onSelect(cluster.largest);
  }, [onSelect]);

  if (!shorelines) return null;

  return <>
    <Pane name="lakePane" style={{ zIndex: 450 }}>
      <GeoJSON key={`lakes-${zoom}-${shorelines.features.length}`} data={shorelines} renderer={renderer}
        style={{ color: '#087fb7', weight: 1.1, fillColor: '#69bfdf', fillOpacity: 0.28 }}
        onEachFeature={(feature, layer) => {
          layer.bindTooltip(feature.properties.display_name, { sticky: true });
          layer.on('click', () => onSelect(feature.properties));
        }} />
    </Pane>

    {/* Symbols and their names sit in Leaflet's marker and tooltip panes, which
        are above the basin overlay, the rivers and this layer's own shorelines.
        The names were previously only reachable by hovering, so at a glance the
        map showed water with nothing identifying it. */}
    {clusters.map(cluster => {
      const label = lakeClusterLabel(cluster);
      return <Marker key={cluster.key} position={[cluster.latitude, cluster.longitude]}
        icon={cluster.count > 1 ? groupIcon(cluster.count) : singleIcon}
        title={label} eventHandlers={{ click: () => open(cluster) }}>
        <Tooltip permanent={named.has(cluster.key)} direction="right"
          offset={[cluster.count > 1 ? (W + 8) / 2 : W / 2 + 1, 0]}
          className={named.has(cluster.key) ? 'land-lake-name' : 'land-lake-hint'}>
          {named.has(cluster.key) ? label
            : `${label} · ${formatNumber(Number(cluster.largest.area_km2), 2)} km²`}
        </Tooltip>
      </Marker>;
    })}
  </>;
}
