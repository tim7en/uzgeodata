import React, { useState } from 'react';
import { CircleMarker, GeoJSON, ImageOverlay, MapContainer, ScaleControl, TileLayer, Tooltip } from 'react-leaflet';

export default function CaseStudyMap({ data, geometry, environment }) {
  const [layer, setLayer] = useState('terrain');
  const c = data.catchment, meta = environment.profile_metadata;
  const stations = [...new Map(data.inventory.map(r => [r.station_id, r])).values()];
  return <section className="cs-panel cs-study-map-panel">
    <div className="cs-section-head"><div><span className="cs-eyebrow">PSKEM / WESTERN TIAN SHAN</span><h2>The terrain behind the time series.</h2></div><div className="cs-switch" aria-label="Study map layer">{[['terrain','Elevation'],['landcover','Land cover · 2025']].map(([v,l])=><button key={v} aria-pressed={layer===v} onClick={()=>setLayer(v)}>{l}</button>)}</div></div>
    <div className="cs-map cs-study-map"><MapContainer bounds={meta.map_bounds} boundsOptions={{padding:[30,30]}} scrollWheelZoom={false} aria-label="Pskem terrain, land cover and observation stations">
      <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}" attribution="Tiles © Esri and contributors"/>
      <ImageOverlay key={layer} url={`/data/case-studies/pskem-${layer==='terrain'?'elevation':'landcover'}-overview.png`} bounds={meta.map_bounds} opacity={.9} attribution={layer==='terrain'?'Copernicus DEM 2024_1':'Esri / Impact Observatory / Microsoft, CC BY 4.0'}/>
      {layer==='terrain'&&<ImageOverlay url="/data/case-studies/pskem-terrain-overview.png" bounds={meta.map_bounds} opacity={.22}/>}
      <GeoJSON data={geometry} style={{color:'#124d61',weight:1.2,fillOpacity:0}}/>
      {stations.map(r=><CircleMarker key={r.station_id} center={[r.latitude,r.longitude]} radius={6} pathOptions={{color:'#fff',weight:2,fillColor:'#ad4f12',fillOpacity:1}}><Tooltip permanent direction="top" className="cs-station-label">{r.station}</Tooltip></CircleMarker>)}
      <CircleMarker center={[c.gauge_latitude,c.gauge_longitude]} radius={8} pathOptions={{color:'#fff',weight:2,fillColor:'#a42b47',fillOpacity:1}}><Tooltip permanent direction="bottom" className="cs-station-label">Pskem–Mullala · location unresolved</Tooltip></CircleMarker>
      <ScaleControl position="bottomleft" imperial={false}/>
    </MapContainer><div className="cs-north" aria-label="North">N ↑</div><div className="cs-map-key">{layer==='terrain'?<><strong>Elevation · metres</strong><div className="cs-elevation-ramp"/><span>800 <span>2,500</span> 4,500</span></>:<><strong>10 m land cover · 2025</strong><div className="cs-map-classes">{Object.entries(meta.classes).filter(([k])=>k!=='10').map(([k,v])=><span key={k}><i style={{background:meta.class_colors[k]}}/>{v}</span>)}</div></>}</div></div>
    <div className="cs-map-caption"><p><strong>{Number(c.area_km2).toLocaleString('en',{maximumFractionDigits:1})} km²</strong> · {c.basin_count} connected level-12 units. This is a provisional upstream domain, including cross-border headwaters. Overview images are display rasters; the land-cover statistics use the native 10 m classes.</p><p><strong className="cs-warning">Gauge assignment needs review.</strong> The stored coordinate lies beside an 11.7 km² tributary; mapped Pskem main-stem reaches lie about 700 m away. The boundary and model results remain exploratory.</p></div>
    <a href="/data/case-studies/pskem-candidate-catchment.geojson" download>Download provisional catchment ↗</a>
  </section>;
}
