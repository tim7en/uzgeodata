import React, { useEffect, useMemo, useState } from 'react';
import { CircleMarker, GeoJSON, MapContainer, ScaleControl, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { basinCatchment } from './basinCatchmentModel.js';
import { formatNumber } from './landingModel.js';

function FitCatchment({ bounds }) {
  const map = useMap();
  useEffect(() => {
    const fit = () => { map.invalidateSize(); map.fitBounds(bounds, { padding: [20, 20], maxZoom: 12, animate: false }); };
    const observer = new ResizeObserver(fit);
    observer.observe(map.getContainer());
    fit();
    return () => observer.disconnect();
  }, [bounds, map]);
  return null;
}

export default function BasinCatchment({ basin, collection, url }) {
  const [loaded, setLoaded] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (collection || !url) return;
    const controller = new AbortController();
    setError('');
    fetch(url, { signal: controller.signal }).then(response => {
      if (!response.ok) throw Error('Catchment geometry is unavailable.');
      return response.json();
    }).then(setLoaded).catch(cause => {
      if (cause.name !== 'AbortError') setError('Catchment geometry could not load.');
    });
    return () => controller.abort();
  }, [collection, url, retry]);
  const geometry = collection || loaded;
  const catchment = useMemo(() => basinCatchment(geometry, basin), [geometry, basin]);
  const selectedBounds = catchment?.selectedBounds;
  const marker = selectedBounds && [
    (selectedBounds[0][0] + selectedBounds[1][0]) / 2,
    (selectedBounds[0][1] + selectedBounds[1][1]) / 2,
  ];
  return <aside className="land-catchment" aria-label="Selected basin and upstream catchment">
    <h3>Upstream catchment</h3>
    {error && !geometry ? <p role="alert">{error} <button onClick={() => setRetry(value => value + 1)}>Retry map</button></p>
      : !geometry ? <p role="status">Loading catchment map…</p>
      : !catchment?.bounds ? <p>No catchment geometry is available for this basin.</p>
      : <>
        <MapContainer className="land-catchment-map" bounds={catchment.bounds} preferCanvas
          scrollWheelZoom={false} attributionControl zoomControl>
          <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'/>
          <GeoJSON data={catchment.upstream} interactive={false}
            style={{ color: '#087b9c', weight: 0.7, fillColor: '#21b9d3', fillOpacity: 0.38 }}/>
          <GeoJSON data={catchment.selected} interactive={false}
            style={{ color: '#9c3d05', weight: 2.5, fillColor: '#ffab46', fillOpacity: 0.8 }}/>
          {marker && <CircleMarker center={marker} radius={5}
            pathOptions={{ color: '#713004', weight: 2, fillColor: '#ffab46', fillOpacity: 1 }}>
            <Tooltip>Selected basin {basin.hybas_id} (location marker)</Tooltip>
          </CircleMarker>}
          <FitCatchment bounds={catchment.bounds}/>
          <ScaleControl imperial={false}/>
        </MapContainer>
        <div className="land-catchment-key">
          <span><i className="selected"/>Selected basin</span>
          <span><i className="upstream"/>Upstream basins</span>
        </div>
        <p>{catchment.count ? `${formatNumber(catchment.count)} upstream basins` : 'Headwater basin: no upstream basins in this network'}.
          {' '}{formatNumber(catchment.areaKm2)} km² traced, including the selected basin.</p>
        {catchment.partial && <p role="note">The mapped network covers part of the reported {formatNumber(basin.upstream_km2)} km² catchment.</p>}
        <small>HydroBASINS drainage links · level {basin.basin_level}. Simplified outlines; the orange marker locates the selected polygon.</small>
      </>}
  </aside>;
}
