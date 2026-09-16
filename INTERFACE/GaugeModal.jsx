import React, { useEffect, useState } from 'react';
import { Download, ExternalLink, X } from 'lucide-react';
import { formatNumber } from './landingModel.js';
import './damModal.css';

/**
 * CA-discharge gauge station modal.
 * 
 * Displays discharge gauge information including discharge measurements, basin
 * characteristics, time series coverage and links to research evidence.
 */
export default function GaugeModal({ gauge, onClose }) {
  useEffect(() => {
    const close = event => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [onClose]);

  const value = v => v === '' || v == null ? '—' : formatNumber(Number(v));
  const getCountryName = code => {
    const countries = {
      'AFG': 'Afghanistan', 'KAZ': 'Kazakhstan', 'KGZ': 'Kyrgyzstan',
      'TJK': 'Tajikistan', 'TKM': 'Turkmenistan', 'UZB': 'Uzbekistan'
    };
    return countries[code] || code;
  };

  const hasTimeSeries = gauge.has_ts === true || gauge.has_ts === 'true';
  const tsStart = gauge.ts_start ? new Date(gauge.ts_start).getFullYear() : null;
  const tsEnd = gauge.ts_end ? new Date(gauge.ts_end).getFullYear() : null;
  const span = tsStart && tsEnd ? `${tsStart}–${tsEnd}` : 'not recorded';

  return <div className="dam-modal gauge-modal" role="dialog" aria-modal="true"
    aria-label={`Discharge gauge ${gauge.name_eng || gauge.code}`} onClick={onClose}>
    <div className="dam-modal-card" onClick={event => event.stopPropagation()}>
      <button className="dam-modal-close" aria-label="Close" onClick={onClose}><X size={15}/></button>

      <header>
        <span className="dam-modal-kicker">
          CA-discharge research dataset · {getCountryName(gauge.country)}
        </span>
        <h2>{gauge.name_eng || gauge.code}</h2>
        <p className="dam-modal-sub">
          {gauge.river ? `On the ${gauge.river}` : 'River not recorded'}.
          {hasTimeSeries ? ` Time series recorded, ${span}.` : ' No time series available.'}
        </p>
      </header>

      <dl className="dam-modal-figures">
        <div><dt>Gauge code</dt><dd><code>{gauge.code}</code></dd></div>
        {gauge.q_m3s ? <div><dt>Mean discharge</dt><dd>{value(gauge.q_m3s)} <em>m³/s</em></dd></div> : null}
        {hasTimeSeries ? <>
          <div><dt>Time series period</dt><dd>{span}</dd></div>
          <div><dt>Complete observations</dt><dd>{value(gauge.n_complete)}</dd></div>
          {gauge.n_miss ? <div><dt>Missing values</dt><dd>{value(gauge.n_miss)} ({value(gauge.n_propmiss * 100)}%)</dd></div> : null}
        </> : <div><dt>Data available</dt><dd>Gauge location only</dd></div>}
        {gauge.basin ? <div><dt>Basin</dt><dd>{gauge.basin}</dd></div> : null}
        {gauge.source ? <div><dt>Original source</dt><dd>{gauge.source}</dd></div> : null}
      </dl>

      <section className="dam-modal-block">
        <h3>About this dataset</h3>
        <p>
          This gauge is part of the CA-discharge dataset: a compiled collection of
          295 discharge gauge locations across mountainous regions in Central Asia.
          The dataset was published by Marti et al. (2023) in Scientific Data.
        </p>
        <p>
          The research summary includes a consistency check between this gauge and
          local station records where overlapping observations exist. The regional
          gauge inventory serves as a validation candidate for discharge modelling
          and a crosswalk for matching stations across archives.
        </p>
      </section>

      <section className="dam-modal-block">
        <h3>Access the research</h3>
        <div className="gauge-modal-links">
          <a href="https://www.nature.com/articles/s41597-023-02474-8" target="_blank" rel="noreferrer">
            Read the paper <ExternalLink size={12}/>
          </a>
          <a href="https://doi.org/10.5281/zenodo.8147591" target="_blank" rel="noreferrer">
            View on Zenodo <ExternalLink size={12}/>
          </a>
          <a href="/data-lineage.html#tree" target="_blank" rel="noreferrer">
            Data lineage tree <ExternalLink size={12}/>
          </a>
        </div>
        <p><small>License: CC BY 4.0 · Citation: Marti, B., et al. (2023)</small></p>
      </section>

      <section className="dam-modal-block">
        <h3>Related datasets</h3>
        <ul style={{ fontSize: '0.95rem', lineHeight: '1.6', margin: '0.5rem 0', paddingLeft: '1.2rem' }}>
          <li><strong>CA-discharge GeoPackage:</strong> Complete gauge registry with basin attributes</li>
          <li><strong>Pskem consistency check:</strong> 555 paired observations validating gauge 16290 overlap</li>
          <li><strong>Research summary:</strong> Import statistics and quality metrics</li>
        </ul>
        <p><small style={{ color: '#666', marginTop: '0.8rem' }}>
          Regional validation studies and modelling integrations available in research documentation.
        </small></p>
      </section>
    </div>
  </div>;
}
