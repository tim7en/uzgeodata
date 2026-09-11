import React, { useMemo, useState } from 'react';
import { Marker, Pane, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import { divIcon } from 'leaflet';
import { clusterStations, formatNumber, withinBounds } from './landingModel.js';

/**
 * Meteorological stations as a selectable layer.
 *
 * A station is a point instrument, so unlike a dam bubble or a lake symbol its mark
 * carries no magnitude: size would imply an extent it does not have. What the symbol
 * does encode is where the coordinate came from, because that is the thing a reader
 * has to weigh before trusting the point. A filled mark is a station whose source
 * published its coordinate; a hollow one was placed by matching a name, and a ringed
 * one departed from the check that tested those matches.
 *
 * Overlapping stations are grouped. Three hundred marks cost nothing to draw, but at
 * national zoom the network is dense enough that they cover one another, and a covered
 * mark cannot be clicked because its neighbour takes the pointer. Grouping is what
 * makes them selectable.
 */
const SIZE = 13;

const symbol = (fill, stroke, ring) =>
  `<svg viewBox="0 0 ${SIZE} ${SIZE}" aria-hidden="true">`
  + (ring ? `<circle cx="${SIZE / 2}" cy="${SIZE / 2}" r="${SIZE / 2 - 0.8}" fill="none" stroke="${ring}" stroke-width="1.3"/>` : '')
  + `<path d="M${SIZE / 2} 2.6 L${SIZE - 3.1} ${SIZE - 3} L3.1 ${SIZE - 3} Z"`
  + ` fill="${fill}" stroke="${stroke}" stroke-width="1.2" stroke-linejoin="round"/>`
  + '</svg>';

// Placement, not measurement: what the reader needs before using the point.
const MARKS = {
  coordinate_supplied_by_source: symbol('#ffd27f', '#5a3d00', null),
  consistent_with_network: symbol('#0a1a24', '#ffd27f', null),
  departs_from_network_relationship: symbol('#0a1a24', '#ff9d7f', '#ff6b4a'),
  not_checked: symbol('#0a1a24', '#9fb3bf', null),
};

const groupSymbol = (count, stroke) =>
  `<svg viewBox="0 0 ${SIZE + 7} ${SIZE + 7}" aria-hidden="true">`
  + `<circle cx="${(SIZE + 7) / 2}" cy="${(SIZE + 7) / 2}" r="${(SIZE + 5) / 2}"`
  + ` fill="#0a1a24" stroke="${stroke}" stroke-width="1.2" opacity="0.93"/>`
  + `<text x="${(SIZE + 7) / 2}" y="${(SIZE + 7) / 2 + 3.3}" text-anchor="middle"`
  + ` font-family="Barlow Condensed, sans-serif" font-size="9" font-weight="700"`
  + ` fill="#ffe9c2">${count}</text></svg>`;

const GROUP_STROKE = {
  coordinate_supplied_by_source: '#ffd27f', consistent_with_network: '#ffd27f',
  departs_from_network_relationship: '#ff6b4a', not_checked: '#9fb3bf',
};

const icons = new Map();
const iconFor = (status, count) => {
  const key = `${MARKS[status] ? status : 'not_checked'}:${count > 1 ? count : 1}`;
  if (!icons.has(key)) {
    const single = count <= 1;
    const size = single ? SIZE : SIZE + 7;
    icons.set(key, divIcon({
      className: `land-station-symbol${single ? '' : ' land-station-group'}`,
      html: single ? (MARKS[status] || MARKS.not_checked)
        : groupSymbol(count, GROUP_STROKE[status] || GROUP_STROKE.not_checked),
      iconSize: [size, size], iconAnchor: [size / 2, size / 2],
    }));
  }
  return icons.get(key);
};

function useView() {
  const map = useMap();
  const read = () => {
    const bounds = map.getBounds().pad(0.25);
    return {
      bounds: [[bounds.getSouth(), bounds.getWest()], [bounds.getNorth(), bounds.getEast()]],
      zoom: map.getZoom(),
    };
  };
  const [view, setView] = useState(read);
  useMapEvents({ moveend: () => setView(read()), zoomend: () => setView(read()) });
  return view;
}

export default function StationLayer({ data, onSelect }) {
  const { bounds, zoom } = useView();

  const visible = useMemo(() => {
    if (!data) return [];
    // withinBounds reads a [longitude, latitude] pair, which is exactly what a
    // GeoJSON point already carries.
    return data.features.filter(feature => withinBounds(feature.geometry.coordinates, bounds));
  }, [data, bounds]);

  const clusters = useMemo(() => clusterStations(visible, zoom), [visible, zoom]);

  if (!data) return null;

  return <Pane name="stationPane" style={{ zIndex: 460 }}>
    {clusters.map(cluster => {
      const grouped = cluster.count > 1;
      const station = cluster.fullest;
      const label = grouped ? `${cluster.count} stations · ${station.name} and others` : station.name;
      const offset = (grouped ? SIZE + 7 : SIZE) / 2 + 1;
      return <Marker key={cluster.key} position={[cluster.latitude, cluster.longitude]}
        icon={iconFor(cluster.placement_status, cluster.count)} title={label}
        eventHandlers={{ click: () => onSelect(station) }}>
        {/* Names only once the map is close enough that they will not collide. */}
        <Tooltip permanent={!grouped && zoom >= 9} direction="right" offset={[offset, 0]}
          className={!grouped && zoom >= 9 ? 'land-station-name' : 'land-station-hint'}>
          {grouped ? `${label} · ${formatNumber(cluster.observations)} monthly values`
            : `${station.name} · ${station.elevation_m == null ? 'elevation not recorded'
              : `${Math.round(station.elevation_m)} m`}`}
        </Tooltip>
      </Marker>;
    })}
  </Pane>;
}
