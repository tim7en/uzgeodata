import React, { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';

// One level-12 basin's water years, 1961-2025, from the drought case study.
const BASE = '/data/atlas/drought-study/basins/';
const RAMP = ['--l-dr-d3', '--l-dr-d2', '--l-dr-d1', '--l-dr-n0', '--l-dr-w1', '--l-dr-w2', '--l-dr-w3'];
const SCALES = { pct: [-40, -25, -10, 10, 25, 40], spi: [-2, -1.5, -1, 1, 1.5, 2], pdsi: [-4, -3, -2, 2, 3, 4] };
const NORMS = [
  ['wmo', '1991–2020', 'ppt_anom_pct_wmo'],
  ['t10', 'Previous 10 yr', 'ppt_anom_pct_trailing_10'],
  ['t20', 'Previous 20 yr', 'ppt_anom_pct_trailing_20'],
  ['t30', 'Previous 30 yr', 'ppt_anom_pct_trailing_30'],
  ['early', '1961–1990', 'ppt_anom_pct_early'],
];
const METRICS = [
  ['anomaly', 'Precipitation vs norm', 'pct', '%'],
  ['spi12', 'SPI-12', 'spi', ''],
  ['pdsi', 'PDSI', 'pdsi', ''],
  ['up_q_anom_pct_wmo', 'Upstream supply', 'pct', '%'],
];

const fmt = (v, digits = 0) => v == null || !Number.isFinite(v) ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(digits)}`.replace('-', '−');
const fill = (v, scale) => { if (v == null || !Number.isFinite(v)) return 'transparent'; let i = 0; while (i < scale.length && v > scale[i]) i++; return `var(${RAMP[i]})`; };

function save(name, contents) {
  const url = URL.createObjectURL(new Blob([contents], { type: 'text/csv;charset=utf-8' }));
  const link = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function csv(record) {
  const lines = [['basin_id', ...record.fields].join(',')];
  for (const row of record.rows) lines.push([record.basin_id, ...row.map(v => v ?? '')].join(','));
  return lines.join('\n') + '\n';
}

function Chart({ record, field, scaleKey, unit, label }) {
  const [hover, setHover] = useState(null);
  const F = useMemo(() => Object.fromEntries(record.fields.map((f, i) => [f, i])), [record]);
  const rows = record.rows;
  const first = rows[0][F.water_year], n = rows.length;
  const W = 780, H = 220, P = { l: 44, r: 10, t: 14, b: 24 };
  const bw = (W - P.l - P.r) / n;
  const values = rows.map(r => r[F[field]]).filter(Number.isFinite);
  const limit = scaleKey === 'pct' ? Math.max(50, Math.ceil(Math.max(...values.map(Math.abs), 0) / 25) * 25)
    : scaleKey === 'spi' ? 3 : Math.max(5, Math.ceil(Math.max(...values.map(Math.abs), 0)));
  const y = v => P.t + (limit - Math.max(-limit, Math.min(limit, v))) / (2 * limit) * (H - P.t - P.b);
  const ticks = [-limit, -limit / 2, 0, limit / 2, limit];
  const picked = hover == null ? null : rows[hover];
  return <figure className="land-drought-chart">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label} by water year`}
      onMouseLeave={() => setHover(null)} onMouseMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        const position = (event.clientX - box.left) / box.width * W;
        setHover(Math.max(0, Math.min(n - 1, Math.floor((position - P.l) / bw))));
      }}>
      {ticks.map(t => <g key={t}>
        <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="land-hist-grid"/>
        <text x={P.l - 6} y={y(t) + 3} textAnchor="end" className="land-hist-axis">{fmt(t, scaleKey === 'spi' ? 1 : 0)}{unit}</text>
      </g>)}
      {record.documented_years.map(e => <line key={`${e.water_year}${e.kind}`} className={`land-drought-event ${e.kind}`}
        x1={P.l + (e.water_year - first + .5) * bw} x2={P.l + (e.water_year - first + .5) * bw} y1={P.t} y2={H - P.b}/>)}
      {rows.map((r, i) => {
        const v = r[F[field]];
        if (!Number.isFinite(v)) return null;
        return <rect key={i} x={P.l + i * bw + .5} width={Math.max(1, bw - 1)} y={Math.min(y(v), y(0))}
          height={Math.max(1, Math.abs(y(v) - y(0)))} rx="1" fill={fill(v, SCALES[scaleKey])}/>;
      })}
      {rows.filter(r => r[F.water_year] % 10 === 0).map(r => <text key={r[F.water_year]} className="land-hist-axis" textAnchor="middle"
        x={P.l + (r[F.water_year] - first + .5) * bw} y={H - 8}>{r[F.water_year]}</text>)}
      {hover != null && <line className="land-hist-cursor" x1={P.l + (hover + .5) * bw} x2={P.l + (hover + .5) * bw} y1={P.t} y2={H - P.b}/>}
    </svg>
    <figcaption>{picked
      ? `WY ${picked[F.water_year]} · ${label} ${fmt(picked[F[field]], scaleKey === 'pct' ? 0 : 2)}${unit} · precipitation ${Math.round(picked[F.ppt])} mm · SPI ${fmt(picked[F.spi12], 2)}`
      : `${label} by water year (October–September). Dashed lines mark documented dry (brown) and wet (teal) years.`}</figcaption>
  </figure>;
}

export default function BasinDrought({ basin }) {
  const [state, setState] = useState({ loading: true });
  const [metric, setMetric] = useState('anomaly');
  const [norm, setNorm] = useState('wmo');
  useEffect(() => {
    let live = true;
    setState({ loading: true });
    fetch(`${BASE}${basin.hybas_id}.json`).then(response => {
      if (!response.ok || !(response.headers.get('content-type') || '').includes('json')) throw Error('The drought record is not published for this basin.');
      return response.json();
    }).then(record => {
      if (String(record.basin_id) !== String(basin.hybas_id)) throw Error('The drought record has the wrong basin identifier.');
      if (live) setState({ record });
    }).catch(error => { if (live) setState({ error: error.message }); });
    return () => { live = false; };
  }, [basin.hybas_id]);
  if (state.loading) return <p role="status" className="land-group-note">Loading the 1961–2025 drought record…</p>;
  if (state.error) return <p role="alert" className="land-group-note">{state.error}</p>;
  const record = state.record;
  const F = Object.fromEntries(record.fields.map((f, i) => [f, i]));
  const [, metricLabel, scaleKey, unit] = METRICS.find(m => m[0] === metric);
  const normEntry = NORMS.find(n => n[0] === norm);
  const field = metric === 'anomaly' ? normEntry[2] : metric;
  const label = metric === 'anomaly' ? `Precipitation vs ${normEntry[1].toLowerCase()}` : metricLabel;
  const recent = record.rows.filter(r => r[F.water_year] >= 1991 && Number.isFinite(r[F.spi12]));
  const severe = recent.filter(r => r[F.spi12] <= -1.5).length;
  const worst = recent.reduce((a, b) => (b[F.spi12] < a[F.spi12] ? b : a), recent[0]);
  const last = record.rows[record.rows.length - 1];
  return <div className="land-drought">
    <p className="land-hist-warn">Water years from TerraClimate v1.1, one product version for 1961–2025. SPI-12 is fitted on 1991–2020. This is a separate product from the Climate 2025–26 tab and is not joined to it.</p>
    <div className="land-drought-stats">
      <div><b>{Math.round(record.norms_mm.wmo_1991_2020)} mm</b><span>1991–2020 normal ({fmt((record.norms_mm.wmo_1991_2020 - record.norms_mm.early_1961_1990) / record.norms_mm.early_1961_1990 * 100, 1)}% vs 1961–1990)</span></div>
      <div><b>{severe}</b><span>severe drought years since 1991 (SPI ≤ −1.5)</span></div>
      <div><b>{worst ? worst[F.water_year] : '–'}</b><span>driest since 1991, SPI {worst ? fmt(worst[F.spi12], 2) : '–'}</span></div>
      <div><b>{fmt(last[F.ppt_anom_pct_wmo])}%</b><span>WY {last[F.water_year]} vs 1991–2020</span></div>
    </div>
    <div className="land-drought-controls">
      <div className="land-sub-chips" role="group" aria-label="Drought measure">
        {METRICS.map(([key, name]) => <button type="button" key={key} className={key === metric ? 'active' : ''} aria-pressed={key === metric} onClick={() => setMetric(key)}>{name}</button>)}
      </div>
      {metric === 'anomaly' && <div className="land-sub-chips" role="group" aria-label="Compare against">
        {NORMS.map(([key, name]) => <button type="button" key={key} className={key === norm ? 'active' : ''} aria-pressed={key === norm} onClick={() => setNorm(key)}>{name}</button>)}
      </div>}
    </div>
    <Chart record={record} field={field} scaleKey={scaleKey} unit={unit} label={label}/>
    {metric === 'up_q_anom_pct_wmo' && <p className="land-sub-note">Runoff generated over the whole catchment above this basin, against its 1991–2020 normal. It counts rain and snowmelt only, with no glacier melt or reservoir releases, so it is a supply signal, not river flow.</p>}
    {metric === 'anomaly' && norm.startsWith('t') && <p className="land-sub-note">A trailing norm is the mean of the water years just before each year, so it needs 10, 20 or 30 earlier years and starts in 1971, 1981 or 1991.</p>}
    <div className="land-drought-actions">
      <button type="button" className="land-hist-download" onClick={() => save(`basin-${basin.hybas_id}-drought.csv`, csv(record))}><Download size={12}/> Download water years (CSV)</button>
      <a href={`${BASE}${basin.hybas_id}.json`} download>JSON with metadata</a>
      <a href="/drought.html">Read the drought study ↗</a>
    </div>
  </div>;
}
