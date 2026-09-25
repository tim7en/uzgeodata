import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { formatNumber } from './landingModel.js';
import './damModal.css';

const nameOf = row => row.name_en || row.name || `Glacier ${row.glacier_key || row.catalogue_number || 'record'}`;
const measured = (value, digits = 1) => value == null || value === '' || !Number.isFinite(Number(value))
  ? 'Not reported' : formatNumber(Number(value), digits);

export default function GlacierModal({ cluster, onClose }) {
  const [index, setIndex] = useState(0);
  const card = useRef(null);
  const row = cluster.members[index];
  const grouped = cluster.count > 1;
  useEffect(() => {
    const previous = document.activeElement;
    card.current.querySelector('button').focus();
    const keydown = event => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (event.key === 'Tab') {
        const controls = [...card.current.querySelectorAll('button, select, a[href]')];
        const first = controls[0], last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', keydown);
    return () => { document.removeEventListener('keydown', keydown); if (previous?.isConnected) previous.focus(); };
  }, [onClose]);

  const figures = [
    ['Reported area (km²)', measured(row.area_km2, 4)],
    ['Perimeter (m)', measured(row.perimeter_m)],
    ['Minimum elevation (m)', measured(row.elevation_min_m)],
    ['Maximum elevation (m)', measured(row.elevation_max_m)],
    ['Length (m)', measured(row.length_m)],
    ['Survey year', row.inventory_year || 'Not reported'],
  ];
  return <div className="dam-modal glacier-modal" role="dialog" aria-modal="true"
    aria-labelledby="glacier-title" onClick={onClose}>
    <div className="dam-modal-card" ref={card} onClick={event => event.stopPropagation()}>
      <button type="button" className="dam-modal-close" aria-label="Close" onClick={onClose}><X size={15}/></button>
      <header>
        <span className="dam-modal-kicker">Glacier catalogue · {row.catalogue || row.basin || 'Survey record'}</span>
        <h2 id="glacier-title">{nameOf(row)}</h2>
        <p className="dam-modal-sub">Catalogue centre point, not a mapped glacier outline.</p>
      </header>
      {grouped && <section className="dam-modal-block">
        <h3>{formatNumber(cluster.count)} glaciers at this map symbol</h3>
        <label className="glacier-record-picker">Glacier record
          <select value={index} onChange={event => setIndex(Number(event.target.value))}>
            {cluster.members.map((member, i) => <option key={i} value={i}>{nameOf(member)} · {member.catalogue}</option>)}
          </select>
        </label>
      </section>}
      <dl className="dam-modal-figures">{figures.map(([label, value]) =>
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <section className="dam-modal-block">
        <h3>Catalogue details</h3>
        <p>Identifier: {row.glacier_key || row.catalogue_number || 'Not reported'}</p>
        {row.name && row.name !== row.name_en && <p>Original name: {row.name}</p>}
        {row.number_1980 && <p>1980 catalogue number: {row.number_1980}</p>}
        {row.basin && <p>Basin: {row.basin}</p>}
        {row.country && <p>Country code: {row.country}</p>}
        <p>Morphology (as recorded): {row.morphology || 'Not reported'}</p>
        <p>Aspect: {row.aspect || 'Not reported'}</p>
        <p>Centre: {measured(row.latitude, 5)}° N, {measured(row.longitude, 5)}° E</p>
        {row.area_km2 == null && <p>This catalogue does not report area. The map symbol represents glacier count.</p>}
      </section>
      <section className="dam-modal-block">
        <h3>Source</h3>
        <p>{row.source_file || 'Source file not recorded'}{row.source_sheet ? ` · ${row.source_sheet}` : ''}
          {row.source_row ? ` · row ${row.source_row}` : ''}</p>
        <p>These are catalogue measurements, not current monitoring observations.</p>
        <a href={row.catalogue === 'Pskem catalogue' ? '/data/hydroclimate/pskem-glaciers.geojson'
          : '/data/hydroclimate/regional-glaciers.geojson'} download>Download source catalogue (GeoJSON)</a>
      </section>
    </div>
  </div>;
}
