import React, { useMemo, useState } from 'react';
import { Marker, Pane, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import { divIcon } from 'leaflet';
import { clusterGlaciers, formatNumber, glacierBasis, glacierRadius, withinBounds } from './landingModel.js';

/**
 * Glacier catalogues as points, because that is what they are.
 *
 * The 2023 Kashkadarya and Surkhandarya workbooks and the Pskem catalogue record
 * one row per glacier with a centre coordinate and no outline. They cover the Hissar
 * ranges and the Pskem headwaters, where the atlas glacier column reports zero and
 * the GLIMS inventory never looked, so without this layer the only glacier evidence
 * the project holds for those provinces is a file nothing draws.
 *
 * What each survey measured differs, and the layer does not paper over it. The two
 * 2023 workbooks report an area; the Pskem catalogue reports a perimeter, an
 * elevation range and a morphology for all 254 of its glaciers and an area for none.
 * So the mark is a circle - never a polygon, which would claim an extent nobody
 * measured - sized by area where there is one and by glacier count where there is
 * not, with a dashed edge and a tooltip line saying which.
 */
// A dashed edge means the size stands for how many glaciers are here, because that
// catalogue reported no area. Solid means the size is the area it reported. Without
// the distinction one scale would silently carry two different quantities.
const ice = (radius, basis) => {
  const size = radius * 2 + 4;
  const centre = size / 2;
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">`
    + `<circle cx="${centre}" cy="${centre}" r="${radius}" fill="rgba(158,226,255,0.42)"`
    + ' stroke="#9ee2ff" stroke-width="1.4"'
    + `${basis === 'count' ? ' stroke-dasharray="3 2"' : ''}/>`
    + '</svg>';
};

export default function GlacierLayer({ data, onSelect }) {
  const map = useMap();
  const readView = () => {
    const bounds = map.getBounds().pad(0.25);
    return {
      zoom: map.getZoom(),
      bounds: [[bounds.getSouth(), bounds.getWest()], [bounds.getNorth(), bounds.getEast()]],
    };
  };
  const [{ zoom, bounds }, setView] = useState(readView);
  useMapEvents({
    zoomend: () => setView(readView()),
    moveend: () => setView(readView()),
  });

  const clusters = useMemo(() => clusterGlaciers(data?.features || [], zoom), [data, zoom]);
  const drawn = useMemo(
    () => clusters.filter(cluster => withinBounds([cluster.longitude, cluster.latitude], bounds)),
    [clusters, bounds],
  );

  return <Pane name="glacier-catalogue" style={{ zIndex: 620 }}>
    {drawn.map(cluster => {
      const radius = glacierRadius(cluster);
      const basis = glacierBasis(cluster);
      const size = radius * 2 + 4;
      const name = cluster.largest?.name_en || cluster.largest?.name || cluster.largest?.glacier_key;
      const elevation = cluster.largest?.elevation_min_m && cluster.largest?.elevation_max_m
        ? `${formatNumber(cluster.largest.elevation_min_m)}–${formatNumber(cluster.largest.elevation_max_m)} m`
        : null;
      return <Marker key={cluster.key} position={[cluster.latitude, cluster.longitude]}
        title={cluster.count > 1 ? `${cluster.count} glaciers` : name || 'Glacier'}
        eventHandlers={{ click: () => onSelect(cluster) }}
        icon={divIcon({
          className: 'land-glacier-mark',
          html: ice(radius, basis),
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        })}>
        <Tooltip direction="top" offset={[0, -radius]}>
          <strong>{cluster.count > 1 ? `${formatNumber(cluster.count)} glaciers` : name || 'Glacier'}</strong>
          {basis === 'area'
            ? <span>{formatNumber(cluster.areaKm2, 2)} km² reported</span>
            : <span>Area not reported in this catalogue{cluster.count > 1 ? '; size shows the count' : ''}</span>}
          {basis === 'count' && elevation && cluster.count === 1 && <span>{elevation}</span>}
          {/* Named so a reader can tell which survey they are looking at: the two
              catalogues were made by different people in different years. */}
          <span>{cluster.catalogues.join(' · ') || 'catalogue survey'}</span>
          <span>Catalogue point, not a mapped outline</span>
        </Tooltip>
      </Marker>;
    })}
  </Pane>;
}
