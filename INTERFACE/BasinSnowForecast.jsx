import React, { useEffect, useState } from 'react';
import { Download } from 'lucide-react';

// April 1 snow for one level-12 basin, and the tested snow forecast that covers it:
// the nearest scored gauge downstream, from the snow forecast case study.
const BASE = '/data/case-studies/snow-forecast/basins/';
const fmt = (v, digits = 2) => v == null || !Number.isFinite(v) ? '–' : v.toFixed(digits).replace('-', '−');

function save(name, contents) {
  const url = URL.createObjectURL(new Blob([contents], { type: 'text/csv;charset=utf-8' }));
  const link = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function SnowChart({ record, upstream }) {
  const [hover, setHover] = useState(null);
  const F = Object.fromEntries(record.fields.map((f, i) => [f, i]));
  const field = upstream ? 'up_apr1_swe_mm' : 'apr1_swe_mm';
  const normal = record.normal_1991_2020[field];
  const rows = record.rows.filter(r => Number.isFinite(r[F[field]]));
  if (!rows.length || !(Math.max(...rows.map(r => r[F[field]])) > 1)) return <p className="land-sub-note">This area holds almost no April snow in ERA5-Land, so there is no snow signal to forecast from.</p>;
  const W = 780, H = 200, P = { l: 44, r: 10, t: 14, b: 24 };
  const first = rows[0][F.water_year], n = rows.at(-1)[F.water_year] - first + 1, bw = (W - P.l - P.r) / n;
  const top = Math.ceil(Math.max(...rows.map(r => r[F[field]])) / 50) * 50 || 50;
  const y = v => P.t + (1 - v / top) * (H - P.t - P.b);
  const picked = hover == null ? null : rows.find(r => r[F.water_year] === first + hover);
  return <figure className="land-drought-chart">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="April 1 snow water equivalent by water year"
      onMouseLeave={() => setHover(null)} onMouseMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        setHover(Math.max(0, Math.min(n - 1, Math.floor(((event.clientX - box.left) / box.width * W - P.l) / bw))));
      }}>
      {[0, .5, 1].map(f => <g key={f}><line x1={P.l} x2={W - P.r} y1={y(top * f)} y2={y(top * f)} className="land-hist-grid"/>
        <text x={P.l - 6} y={y(top * f) + 3} textAnchor="end" className="land-hist-axis">{Math.round(top * f)}</text></g>)}
      {rows.map(r => { const v = r[F[field]]; return <rect key={r[F.water_year]} x={P.l + (r[F.water_year] - first) * bw + .5} width={Math.max(1, bw - 1)}
        y={y(v)} height={y(0) - y(v)} rx="1" fill={`var(${v >= normal ? '--l-dr-w2' : '--l-dr-d2'})`}/>; })}
      {Number.isFinite(normal) && <line className="land-drought-norm" x1={P.l} x2={W - P.r} y1={y(normal)} y2={y(normal)}/>}
      {rows.filter(r => r[F.water_year] % 10 === 0).map(r => <text key={r[F.water_year]} className="land-hist-axis" textAnchor="middle"
        x={P.l + (r[F.water_year] - first + .5) * bw} y={H - 8}>{r[F.water_year]}</text>)}
      {hover != null && <line className="land-hist-cursor" x1={P.l + (hover + .5) * bw} x2={P.l + (hover + .5) * bw} y1={P.t} y2={H - P.b}/>}
    </svg>
    <figcaption>{picked
      ? `WY ${picked[F.water_year]} · April 1 SWE ${Math.round(picked[F[field]])} mm (normal ${Math.round(normal)} mm)${upstream && Number.isFinite(picked[F.up_apr1_swe_km3]) ? ` · ${fmt(picked[F.up_apr1_swe_km3], 2)} km³ upstream` : ''}`
      : `April 1 snow water equivalent, mm, ${upstream ? 'averaged over the whole upstream catchment' : 'in this basin'}. Line: 1991–2020 normal. Teal above it, brown below.`}</figcaption>
  </figure>;
}

function Hindcast({ gauge }) {
  const rows = gauge.hindcast_april;  // [year, observed, raw, corrected, climatology]
  if (!rows?.length) return null;
  const W = 780, H = 200, P = { l: 44, r: 10, t: 14, b: 24 };
  const vals = rows.flatMap(r => [r[1], r[3], r[4]]);
  const lo = Math.min(...vals) * .9, hi = Math.max(...vals) * 1.05;
  const x = yr => P.l + (yr - rows[0][0]) / Math.max(1, rows.at(-1)[0] - rows[0][0]) * (W - P.l - P.r);
  const y = v => P.t + (hi - v) / (hi - lo) * (H - P.t - P.b);
  return <figure className="land-drought-chart">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Observed and forecast April to September flow at the gauge">
      {[lo, (lo + hi) / 2, hi].map(v => <g key={v}><line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} className="land-hist-grid"/>
        <text x={P.l - 6} y={y(v) + 3} textAnchor="end" className="land-hist-axis">{v.toFixed(v < 10 ? 1 : 0)}</text></g>)}
      <polyline points={rows.map(r => `${x(r[0])},${y(r[4])}`).join(' ')} fill="none" stroke="var(--dim)" strokeWidth="1.5" strokeDasharray="4 4"/>
      <polyline points={rows.map(r => `${x(r[0])},${y(r[3])}`).join(' ')} fill="none" stroke="var(--l-accent-1)" strokeWidth="2"/>
      {rows.map(r => <circle key={r[0]} cx={x(r[0])} cy={y(r[1])} r="2.5" fill="var(--ink)"/>)}
      {rows.filter(r => r[0] % 10 === 0).map(r => <text key={r[0]} className="land-hist-axis" textAnchor="middle" x={x(r[0])} y={H - 8}>{r[0]}</text>)}
    </svg>
    <figcaption>April–September mean flow at {gauge.name}, m³/s. Dots: observed. Blue: the 1 April forecast made from earlier years only. Dashed: the previous 30-year mean.</figcaption>
  </figure>;
}

export default function BasinSnowForecast({ basin }) {
  const [state, setState] = useState({ loading: true });
  const [upstream, setUpstream] = useState(true);
  useEffect(() => {
    let live = true;
    setState({ loading: true });
    fetch(`${BASE}${basin.hybas_id}.json`).then(response => {
      if (!response.ok || !(response.headers.get('content-type') || '').includes('json')) throw Error('The snow forecast record is not published for this basin.');
      return response.json();
    }).then(record => {
      if (String(record.basin_id) !== String(basin.hybas_id)) throw Error('The snow forecast record has the wrong basin identifier.');
      if (live) setState({ record });
    }).catch(error => { if (live) setState({ error: error.message }); });
    return () => { live = false; };
  }, [basin.hybas_id]);
  if (state.loading) return <p role="status" className="land-group-note">Loading April snow and the forecast record…</p>;
  if (state.error) return <p role="alert" className="land-group-note">{state.error}</p>;
  const { record } = state;
  const gauge = record.gauge;
  const skill = gauge?.skill?.['4'];
  const csv = () => [['basin_id', ...record.fields].join(','), ...record.rows.map(r => [record.basin_id, ...r.map(v => v ?? '')].join(','))].join('\n') + '\n';
  return <div className="land-drought">
    <p className="land-hist-warn">Method after Barnhart and colleagues (USGS and Uzhydromet HMRI), who forecast Kashkadarya irrigation-season flow from simulated snow. Here snow comes from ERA5-Land, and skill is tested at gauges on years the model had not seen.</p>
    {gauge ? <div className="land-drought-stats">
      <div><b>{fmt(skill?.operational)}</b><span>1 April forecast skill at {gauge.name}, 1971–{gauge.veg_years[1]} (0 = no better than the 30-year mean)</span></div>
      <div><b>{fmt(skill?.operational_recent)}</b><span>same, 1996 onward</span></div>
      <div><b>{fmt(gauge.skill?.['1']?.operational)}</b><span>1 January forecast skill</span></div>
      <div><b>{gauge.area_km2.toLocaleString()} km²</b><span>{gauge.is_outlet ? 'gauged catchment ending at this basin' : 'gauged catchment containing this basin'}{gauge.regulated_since ? ` · dam since ${gauge.regulated_since}` : ''}</span></div>
    </div> : <p className="land-sub-note">No gauge with a tested forecast lies downstream of this basin. Its April snow is shown below as an input for forecasting ungauged basins later.</p>}
    <div className="land-sub-chips" role="group" aria-label="Snow area">
      {[[true, 'Upstream catchment'], [false, 'This basin']].map(([key, label]) =>
        <button type="button" key={label} className={key === upstream ? 'active' : ''} aria-pressed={key === upstream} onClick={() => setUpstream(key)}>{label}</button>)}
    </div>
    <SnowChart record={record} upstream={upstream}/>
    {gauge && <Hindcast gauge={gauge}/>}
    <div className="land-drought-actions">
      <button type="button" className="land-hist-download" onClick={() => save(`basin-${basin.hybas_id}-april-snow.csv`, csv())}><Download size={12}/> Download April snow (CSV)</button>
      <a href={`${BASE}${basin.hybas_id}.json`} download>JSON with forecast record</a>
      <a href="/snow-forecast">Read the snow forecast study ↗</a>
    </div>
  </div>;
}
