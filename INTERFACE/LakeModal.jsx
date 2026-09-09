import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { formatNumber } from './landingModel.js';
import './damModal.css';

export default function LakeModal({ lake, onClose }) {
  useEffect(()=>{const close=e=>{if(e.key==='Escape')onClose();};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close);},[onClose]);
  const value=v=>v===''||v==null?'—':formatNumber(Number(v));
  return <div className="dam-modal lake-modal" role="dialog" aria-modal="true" aria-label={`Water body ${lake.display_name}`} onClick={onClose}><div className="dam-modal-card" onClick={e=>e.stopPropagation()}>
    <button className="dam-modal-close" aria-label="Close" onClick={onClose}><X size={15}/></button>
    <header><span className="dam-modal-kicker">{lake.water_body_type.replaceAll('_',' ')} · {lake.country||'Country not reported'}</span><h2>{lake.display_name}</h2><p className="dam-modal-sub">Name shown from {lake.display_name_source}. Original HydroLAKES name: {lake.source_name||'not recorded'}.</p></header>
    <dl className="dam-modal-figures">{[['Mapped area',lake.area_km2,'km²'],['Catalogue total volume',lake.total_volume_mcm,'MCM'],['Reservoir storage',lake.storage_volume_mcm,'MCM'],['Mean depth',lake.mean_depth_m,'m'],['Elevation',lake.elevation_m,'m'],['Watershed area',lake.watershed_area_km2,'km²']].map(([label,v,unit])=><div key={label}><dt>{label}</dt><dd>{value(v)} <em>{unit}</em></dd></div>)}</dl>
    <section className="dam-modal-block"><h3>Reservoir cross-reference</h3>{lake.dam_links.length?lake.dam_links.map(r=><div key={r.dam_id} className="land-lake-match"><strong>{r.dam_name||`Dam ${r.dam_id}`}</strong><p>{r.link_method==='nearby_candidate'?'Nearby candidate — identity unconfirmed':'Linked by native source identifier'} · {value(r.distance_to_polygon_m)} m from mapped water polygon.</p><p>GDW reservoir name: {r.reservoir_name||'not recorded'}. {r.spatial_check==='spatial_disagreement'?'Location disagrees with the linked polygon; review this association.':''}</p><p>GDW area {value(r.dam_area_km2)} km²; HydroLAKES area {value(r.lake_area_km2)} km². GDW capacity {value(r.dam_capacity_mcm)} MCM; HydroLAKES reservoir storage {value(r.lake_storage_mcm)} MCM.</p></div>):<p>No native-linked or nearby dam was found in the delivered dam inventory.</p>}</section>
    <section className="dam-modal-block"><h3>Source identifiers</h3><p>HydroLAKES {lake.water_body_id} · GRanD {lake.grand_id||'not recorded'} · level-12 basin {lake.hybas_id_level12}.</p><p>HydroLAKES v1.0. Geometry and volumes are historical catalogue values, not today's shoreline or water level. Different survey dates and definitions can explain property differences.</p><a href="/data/hydroclimate/dam-lake-review.csv" download>Download all reservoir–lake comparisons ↗</a></section>
  </div></div>;
}
