import React, { useMemo, useState } from 'react';
import { Marker, Pane, Tooltip, useMapEvents } from 'react-leaflet';
import { divIcon } from 'leaflet';
import { clusterGlaciers, formatNumber, glacierRadius, withinBounds } from './landingModel.js';

/**
 * Glacier catalogues as points, because that is what they are.
 *
 * The 2023 Kashkadarya and Surkhandarya workbooks and the Pskem catalogue record
 * one row per glacier with a reported area and a centre coordinate; no outline was
 * delivered with them. They cover the Hissar ranges, where the atlas glacier column
 * reports zero and the GLIMS inventory never looked, so without this layer the only
 * glacier evidence the project holds for those provinces is a file nothing draws.
 *
 * The mark is a circle sized by reported area, not a polygon: a filled shape here
 * would claim an extent the survey did not measure.
 */
const ice = (radius, count) => {
  const size = radius * 2 + 4;
  const centre = size / 2;
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">`
    + `<circle cx="${centre}" cy="${centre}" r="${radius}" fill="rgba(158,226,255,0.42)"`
    + ` stroke="#9ee2ff" stroke-width="${count > 1 ? 1.6 : 1.1}"`
    + `${count > 1 ? ' stroke-dasharray="3 2"' : ''}/>`
    + '</svg>';
};

export default function GlacierLayer({ data }) {
  const [zoom, setZoom] = useState(7);
  const [bounds, setBounds] = useState(null);
  const map = useMapEvents({
    zoomend: () => { setZoom(map.getZoom()); setBounds(map.getBounds()); },
    moveend: () => setBounds(map.getBounds()),
  });

  const clusters = useMemo(() => clusterGlaciers(data?.features || [], zoom), [data, zoom]);
  const drawn = useMemo(
    () => clusters.filter(cluster => withinBounds(bounds, cluster.longitude, cluster.latitude)),
    [clusters, bounds],
  );

  return <Pane name="glacier-catalogue" style={{ zIndex: 620 }}>
    {drawn.map(cluster => {
      const radius = glacierRadius(cluster);
      const size = radius * 2 + 4;
      const name = cluster.largest?.name_en || cluster.largest?.name || cluster.largest?.glacier_key;
      return <Marker key={cluster.key} position={[cluster.latitude, cluster.longitude]}
        icon={divIcon({
          className: 'land-glacier-mark',
          html: ice(radius, cluster.count),
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        })}>
        <Tooltip direction="top" offset={[0, -radius]}>
          <strong>{cluster.count > 1 ? `${formatNumber(cluster.count)} glaciers` : name || 'Glacier'}</strong>
          {cluster.areaKm2 > 0 && <span>{formatNumber(cluster.areaKm2, 2)} km² reported</span>}
          {/* Named so a reader can tell which survey they are looking at: the two
              catalogues were made by different people in different years. */}
          <span>{cluster.catalogues.join(' · ') || 'catalogue survey'}</span>
          <span>Catalogue point, not a mapped outline</span>
        </Tooltip>
      </Marker>;
    })}
  </Pane>;
}
