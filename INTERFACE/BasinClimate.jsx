import React, { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';

const BASE = '/data/atlas/climate-continuation/basins/';
const WATER_BALANCE = new Set(['aet', 'def', 'PDSI', 'pet', 'q', 'soil', 'swe', 'vpd']);
const PRODUCT = { 'direct_v1.1': 'TerraClimate v1.1 · direct product',
  'estimated_v1.0': 'ERA adjustment · estimated v1.0 statistic' };

function save(name, contents, type) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const link = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// "2025", or "2025-01 to 2026-08", from the rows actually published for a product.
function span(record, product) {
  const codes = Object.values(record.series).filter(series => series.product === product)
    .flatMap(series => series.rows.map(row => row[0] * 100 + row[1]));
  if (!codes.length) return 'none';
  const label = code => `${Math.floor(code / 100)}-${String(code % 100).padStart(2, '0')}`;
  const low = Math.min(...codes), high = Math.max(...codes);
  return low % 100 === 1 && high % 100 === 12 && high - low === 11
    ? String(Math.floor(low / 100)) : `${label(low)} to ${label(high)}`;
}

function csv(record) {
  const lines = ['basin_id,product,support,variable,year,month,value,unit,coverage_fraction,water_equivalent_mcm,holdout_abs_error_p90'];
  for (const series of Object.values(record.series)) for (const row of series.rows) {
    lines.push([record.basin_id, series.product, series.support, series.variable,
      row[0], row[1], row[2] ?? '', series.unit, row[3] ?? '', row[4] ?? '', row[5] ?? ''].join(','));
  }
  return lines.join('\n') + '\n';
}

function ClimateChart({ direct, estimate, unit }) {
  const [hover, setHover] = useState(null);
  const all = [...(direct?.rows || []), ...(estimate?.rows || [])].filter(row => Number.isFinite(row[2]));
  if (!all.length) return <p>No monthly values for this selection.</p>;
  const min = Math.min(...all.map(row => row[2]));
  const max = Math.max(...all.map(row => row[2]));
  const low = min === max ? min - 1 : min - (max - min) * .08;
  const high = min === max ? max + 1 : max + (max - min) * .08;
  // The axis spans whatever years the record holds, so a new year needs no code change.
  const first = Math.min(...all.map(row => row[0]));
  const months = (Math.max(...all.map(row => row[0])) - first + 1) * 12;
  const step = 712 / (months - 1);
  const index = row => (row[0] - first) * 12 + row[1] - 1;
  const x = row => 48 + index(row) * step;
  const y = row => 194 - (row[2] - low) / (high - low) * 170;
  const polyline = rows => rows.filter(row => Number.isFinite(row[2]))
    .map(row => `${x(row)},${y(row)}`).join(' ');
  const picked = hover == null ? null : [direct, estimate].flatMap(s => s?.rows || [])
    .filter(row => index(row) === hover);
  return <figure className="land-climate-chart">
    <svg viewBox="0 0 780 235" role="img" aria-label="Monthly basin climate, direct TerraClimate and estimated continuation"
      onMouseLeave={() => setHover(null)} onMouseMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        const position = (event.clientX - box.left) / box.width * 780;
        setHover(Math.max(0, Math.min(months - 1, Math.round((position - 48) / step))));
      }}>
      {[0, .5, 1].map((fraction, tick) => <g key={tick}>
        <line x1="48" x2="760" y1={24 + fraction * 170} y2={24 + fraction * 170} className="land-hist-grid"/>
        <text x="42" y={28 + fraction * 170} textAnchor="end" className="land-hist-axis">{(high - fraction * (high - low)).toFixed(1)}</text>
      </g>)}
      {Array.from({ length: months / 12 }, (_, offset) =>
        <text key={offset} x={48 + offset * 12 * step} y="220" className="land-hist-axis">{first + offset}</text>)}
      {direct && <polyline points={polyline(direct.rows)} className="land-climate-direct"/>}
      {estimate && <polyline points={polyline(estimate.rows)} className="land-climate-estimate"/>}
      {hover != null && <line x1={48 + hover * step} x2={48 + hover * step} y1="24" y2="194" className="land-hist-cursor"/>}
    </svg>
    <figcaption>{picked?.length ? `${first + Math.floor(hover / 12)}-${String(hover % 12 + 1).padStart(2, '0')} · ${picked.map(row => `${Number(row[2]).toFixed(2)} ${unit}`).join(' / ')}` : `Monthly values · ${unit}`}</figcaption>
  </figure>;
}

export default function BasinClimate({ basin }) {
  const [state, setState] = useState({ loading: true });
  const [variable, setVariable] = useState('ppt');
  const [support, setSupport] = useState('local');
  useEffect(() => {
    let live = true;
    setState({ loading: true });
    fetch(`${BASE}${basin.hybas_id}.json`, { cache: 'no-store' }).then(response => {
      if (!response.ok || !(response.headers.get('content-type') || '').includes('json')) throw Error('Climate record is not published for this basin.');
      return response.json();
    }).then(record => {
      if (String(record.basin_id) !== String(basin.hybas_id)) throw Error('Climate record has the wrong basin identifier.');
      if (live) setState({ record });
    }).catch(error => { if (live) setState({ error: error.message }); });
    return () => { live = false; };
  }, [basin.hybas_id]);
  const record = state.record;
  const variables = useMemo(() => record ? [...new Set(Object.values(record.series)
    .filter(series => series.support === support).map(series => series.variable === 'precipitation' ? 'ppt' : series.variable))] : [], [record, support]);
  const active = variables.includes(variable) ? variable : variables[0];
  const direct = record?.series[`direct_v1.1:${support}:${active}`];
  const estimate = record?.series[`estimated_v1.0:${support}:${active === 'ppt' ? 'precipitation' : active}`];
  if (state.loading) return <p role="status" className="land-group-note">Loading versioned climate record…</p>;
  if (state.error) return <p role="alert" className="land-group-note">{state.error}</p>;
  return <div className="land-climate">
    <p className="land-hist-warn">TerraClimate v1.1 values ({span(record, 'direct_v1.1')}) are a direct modelled product. The {span(record, 'estimated_v1.0')} values are ERA-based estimates of the older v1.0 statistic. The producer advises against joining these versions into one trend.</p>
    <div className="land-history-actions">
      <button type="button" className="land-hist-download" onClick={() => save(`basin-${basin.hybas_id}-climate.csv`, csv(record), 'text/csv;charset=utf-8')}><Download size={12}/> Download all climate series (CSV)</button>
      <a href={`${BASE}${basin.hybas_id}.json`} download>JSON with metadata</a>
    </div>
    <div className="land-sub-chips" role="group" aria-label="Spatial support">
      {[['local', 'This basin'], ['upstream', 'Upstream area']].map(([key, label]) =>
        <button type="button" key={key} className={key === support ? 'active' : ''} onClick={() => setSupport(key)}>{label}</button>)}
    </div>
    <div className="land-sub-chips" role="group" aria-label="Climate variable">
      {variables.map(key => <button type="button" key={key} className={key === active ? 'active' : ''}
        onClick={() => setVariable(key)}>{(record.series[`direct_v1.1:${support}:${key}`] || record.series[`estimated_v1.0:${support}:${key}`])?.label || key}</button>)}
    </div>
    <div className="land-climate-legend">
      {direct && <span><i className="land-climate-direct-key"/>{PRODUCT['direct_v1.1']}</span>}
      {estimate && <span><i className="land-climate-estimate-key"/>{PRODUCT['estimated_v1.0']}</span>}
    </div>
    <ClimateChart direct={direct} estimate={estimate} unit={(direct || estimate)?.unit}/>
    {support === 'upstream' && <p className="land-sub-note">Upstream values are area weighted over level‑12 basins. CSV/JSON include coverage and water equivalent volumes where applicable. Modelled runoff generation is not routed streamflow.</p>}
    {estimate && <p className="land-sub-note">The CSV includes the river-system 90th percentile of held out absolute error for local ERA estimates. It measures agreement with the older TerraClimate product, not station uncertainty.</p>}
    {estimate && WATER_BALANCE.has(active) && <p className="land-sub-note">This estimate maps the ERA5-Land {active === 'q' ? 'runoff' : 'water and energy'} anomaly onto the TerraClimate v1.0 basin climatology, fitted on 2003–2018 and checked on 2019–2024.{active === 'q' ? ' It is modelled runoff generation, not observed or routed river discharge.' : ''}</p>}
    <p className="land-sub-note"><a href="/data/atlas/climate-continuation/report.json">Validation and source record ↗</a> · <a href="/data/atlas/climate-continuation/water-balance-report.json">Water-balance validation ↗</a></p>
  </div>;
}
