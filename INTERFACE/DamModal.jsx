import React, { useEffect, useState } from 'react';
import { Database, Scale, X } from 'lucide-react';
import { damHeadline, damLabel, damUseLabel, formatNumber, systemMeta } from './landingModel.js';
import './damModal.css';

/**
 * Everything the project holds about one dam, as a modal.
 *
 * The rail card this replaces could show seven fields and no context. A dam is
 * only interesting relative to the network it sits on — which reach it blocks,
 * which reservoir it holds, which basin it stands in, whether that basin is where
 * the runoff forms — so the modal has room to say all of it, and to name the
 * identifiers that let a reader follow the dam into the other tables.
 *
 * Shared by the landing map and the atlas explorer so the two never drift apart.
 */
export default function DamModal({ dam, onClose }) {
  const [review,setReview]=useState(null);
  useEffect(()=>{
    let active=true;setReview(null);
    fetch('/data/hydroclimate/dam-lake-review.json').then(r=>r.ok?r.json():Promise.reject()).then(d=>{if(active)setReview(d.pairs.filter(r=>String(r.dam_id)===String(dam.dam_id)));}).catch(()=>{if(active)setReview([]);});
    return()=>{active=false;};
  },[dam?.dam_id]);
  useEffect(() => {
    const escape = event => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [onClose]);

  if (!dam) return null;
  const rows = damHeadline(dam);
  const uses = (dam.uses || '').split(';').map(entry => entry.trim()).filter(Boolean);
  const formation = Number(dam.in_headwater_formation) === 1;
  const snapped = dam.position_source === 'snapped to the river network';
  const identifiers = [
    ['GDW', dam.dam_id],
    ['GRanD', dam.grand_id],
    ['HydroLAKES', dam.hylak_id],
    ['HydroRIVERS reach', dam.hyriv_id],
    ['Basin, level 12', dam.hybas_id_level12],
  ].filter(([, value]) => value !== '' && value !== null && value !== undefined);

  return <div className="dam-modal" role="dialog" aria-modal="true"
    aria-label={`Dam ${damLabel(dam)}`} onClick={onClose}>
    <div className="dam-modal-card" onClick={event => event.stopPropagation()}>
      <button type="button" className="dam-modal-close" onClick={onClose} aria-label="Close"><X size={15}/></button>

      <header>
        <span className="dam-modal-kicker" style={{ '--system': systemMeta(dam.system_id).color }}>
          {systemMeta(dam.system_id).label} · {dam.country || 'country not reported'}
        </span>
        <h2>{damLabel(dam)}</h2>
        {dam.reservoir_name && dam.reservoir_name !== dam.dam_name
          ? <p className="dam-modal-sub">Reservoir: {dam.reservoir_name}</p> : null}
      </header>

      <dl className="dam-modal-figures">
        {rows.map(row => <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}{row.unit ? <em> {row.unit}</em> : null}</dd>
        </div>)}
      </dl>

      <section className="dam-modal-block">
        <h3>Where it stands</h3>
        <p>
          {formation
            ? 'In a runoff-formation zone — it regulates water where that water is generated.'
            : 'Downstream of the formation zones — it regulates water generated above it.'}
          {dam.degree_of_regulation_pc
            ? ` Upstream storage can hold back ${formatNumber(Number(dam.degree_of_regulation_pc), 1)}% of this river's mean annual flow.`
            : ''}
        </p>
        {uses.length > 1 && <p>Recorded purposes: {uses.join(', ')}.</p>}
        {uses.length <= 1 && dam.main_use && <p>Operated primarily for {damUseLabel(dam).toLowerCase()}.</p>}
      </section>

      <section className="dam-modal-block">
        <h3>Lake and reservoir cross-check</h3>
        {review===null?<p>Loading the lake comparison…</p>:review.length?review.map(r=><div key={r.water_body_id}>
          <p><strong>{r.lake_name||`HydroLAKES ${r.water_body_id} · unnamed in source`}</strong><br/>{r.link_method==='nearby_candidate'?'Nearby candidate, not a confirmed match':'Native source identifier link'} · {formatNumber(r.distance_to_polygon_m)} m from the mapped water polygon.</p>
          <p>Mapped lake area: {formatNumber(r.lake_area_km2)} km²; GDW reservoir area: {formatNumber(r.dam_area_km2)} km². Lake storage: {formatNumber(r.lake_storage_mcm)} MCM; GDW capacity: {formatNumber(r.dam_capacity_mcm)} MCM.</p>
          {r.spatial_check==='spatial_disagreement'&&<p><strong>Location discrepancy:</strong> the linked polygon is over 2 km away. Review the snapped dam position and catalogue association.</p>}
        </div>):<p>No comparison is available in the current lake audit.</p>}
        <a href="/data/hydroclimate/dam-lake-review.csv" download>Download source names, properties and match evidence ↗</a>
      </section>
      <section className="dam-modal-block">
        <h3>Identifiers</h3>
        <dl className="dam-modal-ids">
          {identifiers.map(([label, value]) => <div key={label}>
            <dt>{label}</dt><dd><code>{value}</code></dd>
          </div>)}
        </dl>
        <p className="dam-modal-note">
          <Database size={11}/>
          <span>
            These are the source's own keys, so this dam can be followed straight into the
            reach, lake and basin tables the project already publishes.
          </span>
        </p>
      </section>

      <p className="dam-modal-note">
        <Scale size={11}/>
        <span>
          Global Dam Watch v1.0, CC BY 4.0. Storage is nominal capacity as designed or
          reported, never an operating level: this says how much the reservoir can hold,
          not how full it is today.
          {snapped ? ' This dam has no reported coordinate in the source and is placed on'
            + ' the river centreline, so its marker sits on the channel rather than on the structure.' : ''}
        </span>
      </p>
    </div>
  </div>;
}
