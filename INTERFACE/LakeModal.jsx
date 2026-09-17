import React, { useEffect, useState } from 'react';
import { X, Download } from 'lucide-react';
import { formatNumber } from './landingModel.js';
import Chart from './features/case-studies/TimeSeriesChart.jsx';
import './damModal.css';
import './case-studies.css';

function swotToCsv(swot) {
  const lines = ['date,area_km2,wse_m,n_overpasses'];
  for (const m of swot.months) lines.push([m.time, m.area_km2 ?? '', m.wse_m ?? '', m.n_overpasses].join(','));
  return lines.join('\n') + '\n';
}

function downloadText(text, type, filename) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  requestAnimationFrame(() => URL.revokeObjectURL(url));
}

/** SWOT satellite monitoring, when this water body has a matched record.
 * Fetched lazily per lake rather than bundled with the map layer: only
 * ~250 of the map's 1,393 water bodies have one, and each record is its
 * own small file, the same lazy-fetch shape StationModal already uses. */
function useSwotRecord(waterBodyId) {
  const [state, setState] = useState({ status: 'loading', data: null });
  useEffect(() => {
    let live = true;
    setState({ status: 'loading', data: null });
    fetch(`/data/case-studies/reservoirs/swot/${waterBodyId}.json`, { cache: 'no-store' })
      .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(data => { if (live) setState({ status: 'ready', data }); })
      .catch(() => { if (live) setState({ status: 'none', data: null }); });
    return () => { live = false; };
  }, [waterBodyId]);
  return state;
}

function SwotSection({ waterBodyId, catalogueAreaKm2 }) {
  const { status, data } = useSwotRecord(waterBodyId);
  if (status === 'loading' || status === 'none') return null;
  const rows = data.months.map(m => ({ label: m.time.slice(0, 7), area_km2: m.area_km2, wse_m: m.wse_m }));
  const hasWse = rows.some(r => r.wse_m != null);
  const first = data.months[0], last = data.months[data.months.length - 1];
  // Max over the last 3 available months, not the literal last one: a
  // month can close out with a single overpass that only partially imaged
  // the lake, understating a reservoir that was near full weeks earlier
  // (matches the same choice made for reservoir_summary.csv's latest_area_km2).
  const recentAreas = rows.map(r => r.area_km2).filter(v => v != null).slice(-3);
  const latestArea = recentAreas.length ? Math.max(...recentAreas) : undefined;
  const catalogue = Number(catalogueAreaKm2);
  const compareText = latestArea != null && Number.isFinite(catalogue) && catalogue > 0
    ? ` The HydroLAKES catalogue figure above (${catalogue.toLocaleString('en', { maximumFractionDigits: 0 })} km²) is a historical survey value, not today's extent; the latest SWOT observation here is ${latestArea.toLocaleString('en', { maximumFractionDigits: 0 })} km² (${(100 * (latestArea - catalogue) / catalogue).toLocaleString('en', { maximumFractionDigits: 0, signDisplay: 'always' })}%).`
    : '';
  return <section className="dam-modal-block">
    <h3>Satellite monitoring (SWOT)</h3>
    <p>NASA/CNES's SWOT mission has observed this water body's surface area{hasWse ? ' and level' : ''} by radar, roughly every 21 days, from {first.time.slice(0, 7)} to {last.time.slice(0, 7)}. Values are monthly maxima, because a single overpass often images only part of a large lake and can only under-count its true extent, never over-count it.{compareText}</p>
    <Chart rows={rows} fields={[{ key: 'area_km2', label: 'Surface area', color: '#58c9e5' }]} unit="km²" title="Monthly maximum observed area" />
    {hasWse && <Chart rows={rows} fields={[{ key: 'wse_m', label: 'Water surface elevation', color: '#edb06c' }]} unit="m" title="Monthly water surface elevation" />}
    <div className="station-modal-downloads">
      <button onClick={() => downloadText(swotToCsv(data), 'text/csv;charset=utf-8', `swot-${waterBodyId}.csv`)}><Download size={13}/> CSV</button>
      <button onClick={() => downloadText(JSON.stringify(data, null, 2), 'application/json', `swot-${waterBodyId}.json`)}><Download size={13}/> JSON</button>
    </div>
    <div className="gauge-modal-links"><a href="/reservoir-monitoring.html">Full case study &amp; methodology &#8594;</a></div>
  </section>;
}

export default function LakeModal({ lake, onClose }) {
  useEffect(()=>{const close=e=>{if(e.key==='Escape')onClose();};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close);},[onClose]);
  const value=v=>v===''||v==null?'—':formatNumber(Number(v));
  return <div className="dam-modal lake-modal" role="dialog" aria-modal="true" aria-label={`Water body ${lake.display_name}`} onClick={onClose}><div className="dam-modal-card" onClick={e=>e.stopPropagation()}>
    <button className="dam-modal-close" aria-label="Close" onClick={onClose}><X size={15}/></button>
    <header><span className="dam-modal-kicker">{lake.water_body_type.replaceAll('_',' ')} · {lake.country||'Country not reported'}</span><h2>{lake.display_name}</h2><p className="dam-modal-sub">Name shown from {lake.display_name_source}. Original HydroLAKES name: {lake.source_name||'not recorded'}.</p></header>
    <dl className="dam-modal-figures">{[['Mapped area',lake.area_km2,'km²'],['Catalogue total volume',lake.total_volume_mcm,'MCM'],['Reservoir storage',lake.storage_volume_mcm,'MCM'],['Mean depth',lake.mean_depth_m,'m'],['Elevation',lake.elevation_m,'m'],['Watershed area',lake.watershed_area_km2,'km²']].map(([label,v,unit])=><div key={label}><dt>{label}</dt><dd>{value(v)} <em>{unit}</em></dd></div>)}</dl>
    <SwotSection waterBodyId={lake.water_body_id} catalogueAreaKm2={lake.area_km2} />
    <section className="dam-modal-block"><h3>Reservoir cross-reference</h3>{lake.dam_links.length?lake.dam_links.map(r=><div key={r.dam_id} className="land-lake-match"><strong>{r.dam_name||`Dam ${r.dam_id}`}</strong><p>{r.link_method==='nearby_candidate'?'Nearby candidate — identity unconfirmed':'Linked by native source identifier'} · {value(r.distance_to_polygon_m)} m from mapped water polygon.</p><p>GDW reservoir name: {r.reservoir_name||'not recorded'}. {r.spatial_check==='spatial_disagreement'?'Location disagrees with the linked polygon; review this association.':''}</p><p>GDW area {value(r.dam_area_km2)} km²; HydroLAKES area {value(r.lake_area_km2)} km². GDW capacity {value(r.dam_capacity_mcm)} MCM; HydroLAKES reservoir storage {value(r.lake_storage_mcm)} MCM.</p></div>):<p>No native-linked or nearby dam was found in the delivered dam inventory.</p>}</section>
    <section className="dam-modal-block"><h3>Source identifiers</h3><p>HydroLAKES {lake.water_body_id} · GRanD {lake.grand_id||'not recorded'} · level-12 basin {lake.hybas_id_level12}.</p><p>HydroLAKES v1.0. Geometry and volumes are historical catalogue values, not today's shoreline or water level. Different survey dates and definitions can explain property differences.</p><a href="/data/hydroclimate/dam-lake-review.csv" download>Download all reservoir–lake comparisons ↗</a></section>
  </div></div>;
}
