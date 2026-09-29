import React, { useState } from 'react';
import ThemeToggle from './ThemeToggle.jsx';
import { formatNumber } from './landingModel.js';
import { useWidth } from './ReportChart.jsx';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pct = value => `${Math.round(value * 100)}%`;

/** The site's own header, with the page's sections a tap away. */
export function SiteNav({ sections }) {
  return <header className="seas-nav">
    <div className="seas-nav-top">
      <a href="/" className="land-brand" aria-label="UzGeoData home"><span className="land-brand-icon" aria-hidden="true">&#8776;</span>
        <span className="land-brand-word">UZGEODATA</span><span className="land-brand-sub">BASIN ATLAS</span></a>
      <nav aria-label="Main navigation">
        <a href="/">Basin explorer</a><a href="/drought.html">Drought study</a>
        <a href="/case-studies.html">Case studies</a><a href="/guide.html">Guide</a>
      </nav>
      <ThemeToggle/>
    </div>
    <nav className="seas-toc" aria-label="On this page">
      {sections.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
    </nav>
  </header>;
}

const ZONES = [
  ['zone:amu_darya:headwater', 'Amu Darya headwaters'], ['zone:syr_darya:headwater', 'Syr Darya headwaters'],
  ['zone:amu_darya:lowland', 'Amu Darya lowlands'], ['zone:syr_darya:lowland', 'Syr Darya lowlands'],
];

/**
 * One sentence per zone: the likelier outcome for the season and whether the
 * forecast has earned trust there. A forecast without skill is stated as such
 * first, so its percentage is not the thing a reader carries away.
 */
export function KeyMessages({ forecast }) {
  const season = forecast.windows.find(window => window.id === 'season5') || forecast.windows[0];
  return <div className="seas-keys">{ZONES.map(([key, label]) => {
    const rain = forecast.units[key]?.ppt?.[season.id];
    const heat = forecast.units[key]?.tmean?.[season.id];
    if (!rain || !heat) return null;
    const p = rain.forecast.probabilities;
    const wet = p.above >= p.below;
    const lead = wet ? p.above : p.below;
    return <article key={key} className={rain.skill.useful ? 'seas-key seas-key-skill' : 'seas-key'}>
      <h3>{label}</h3>
      <p className="seas-key-main">{rain.skill.useful
        ? <>{pct(lead)} chance {wet ? 'wetter' : 'drier'} than normal</>
        : <>No reliable precipitation signal</>}</p>
      <p>{season.label} precipitation {rain.skill.useful ? `(skilful, RPSS ${formatNumber(rain.skill.rpss, 2)})`
        : `— the model leans ${wet ? 'wetter' : 'drier'} (${pct(lead)}) but has not beaten climatology here`}.
        {' '}Drought-level season: {pct(rain.forecast.dry_probability)} against 16% normally.</p>
      <p>Temperature: {pct(heat.forecast.probabilities.above)} chance warmer
        {heat.skill.useful ? ' (skilful)' : ' (no skill)'}.</p>
    </article>;
  })}</div>;
}

/** What each part of the record reaches, and when it next moves. */
export function Freshness({ forecast, report }) {
  const next = (() => {
    const [year, month] = forecast.init.split('-').map(Number);
    const index = year * 12 + month;
    return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}-05`;
  })();
  const recordEnd = report ? `${report.held_out_years[1]}-12` : null;
  const rain = report?.validation?.precipitation;
  return <dl className="seas-fresh">
    {recordEnd && <div><dt>TerraClimate v1.1, producer release</dt><dd>2003-01 to {recordEnd}</dd>
      <small>Released once a year; the next yearly file replaces the estimates below.</small></div>}
    {report && <div><dt>Provisional estimates from ERA5-Land</dt><dd>{report.held_out_years[1] + 1}-01 to {report.continuation_through}</dd>
      <small>{rain ? `Held-out precipitation error ${formatNumber(rain.amu_darya.adjusted.rmse, 1)} (Amu) and `
        + `${formatNumber(rain.syr_darya.adjusted.rmse, 1)} (Syr) mm/month, ${report.held_out_years.join('–')}.` : ''}</small></div>}
    <div><dt>SEAS5 seasonal forecast</dt><dd>started {forecast.init}, six months ahead</dd>
      <small>{forecast.members} members; next run about {next}.</small></div>
  </dl>;
}

/**
 * Share of level-7 basins where the forecast beat climatology, by start month:
 * where in the year a forecast is worth reading. Two series, one axis, a legend
 * and direct labels on the bars that carry a message.
 */
export function SkillShareChart({ table, period }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const months = Array.from({ length: 12 }, (_, i) => i + 1);
  const value = (name, month) => table.level7_useful_share?.[name]?.[String(month)]?.[period];
  const height = 200, pad = { top: 12, right: 8, bottom: 24, left: 34 };
  const plot = Math.max(0, width - pad.left - pad.right), tall = height - pad.top - pad.bottom;
  const slot = plot / 12, bar = Math.max(2, (slot - 6) / 2);
  const y = share => pad.top + tall - share * tall;
  return <figure className="seas-chart">
    <ul className="poi-chart-legend">
      <li><i className="seas-key-ppt"/>Precipitation</li><li><i className="seas-key-tmean"/>Mean temperature</li>
    </ul>
    <div ref={ref}>{width > 0 && <svg width={width} height={height} role="img"
      aria-label="Share of level-7 basins where SEAS5 beat climatology, by start month">
      {[0, 0.5, 1].map(tick => <g key={tick}>
        <line x1={pad.left} x2={pad.left + plot} y1={y(tick)} y2={y(tick)} className="poi-chart-grid"/>
        <text x={pad.left - 5} y={y(tick) + 4} textAnchor="end" className="poi-chart-axis">{pct(tick)}</text>
      </g>)}
      {months.map((month, i) => {
        const x = pad.left + i * slot + 3;
        const rain = value('ppt', month), heat = value('tmean', month);
        return <g key={month} onPointerEnter={() => setHover(month)} onPointerDown={() => setHover(month)}>
          <rect x={pad.left + i * slot} y={pad.top} width={slot} height={tall} fill="transparent"/>
          {rain !== undefined && <rect x={x} y={y(rain)} width={bar} height={Math.max(1, tall - (y(rain) - pad.top))} rx={2} className="seas-bar-ppt"/>}
          {heat !== undefined && <rect x={x + bar + 2} y={y(heat)} width={bar} height={Math.max(1, tall - (y(heat) - pad.top))} rx={2} className="seas-bar-tmean"/>}
          {rain === undefined && heat === undefined && <text x={x + slot / 2 - 3} y={y(0) - 4} textAnchor="middle" className="poi-chart-axis">…</text>}
          <text x={pad.left + (i + 0.5) * slot} y={height - 6} textAnchor="middle" className="poi-chart-axis">{MONTHS[i][0]}</text>
        </g>;
      })}
    </svg>}</div>
    <figcaption className="poi-chart-readout">{hover
      ? (value('ppt', hover) === undefined ? `${MONTHS[hover - 1]} start: hindcast not yet collected`
        : `${MONTHS[hover - 1]} start: precipitation beats climatology in ${pct(value('ppt', hover))} of basins, `
          + `temperature in ${pct(value('tmean', hover))}`)
      : 'Touch or hover a month. “…” marks a start month whose hindcast has not yet been collected.'}</figcaption>
  </figure>;
}

const VERSION_ROWS = [
  ['pre_mm_s', 'Precipitation', 'mm/month', 12, 'annual total, mm'],
  ['tmx_dc_s', 'Maximum temperature', '°C', 1, 'annual mean, °C'],
  ['tmn_dc_s', 'Minimum temperature', '°C', 1, 'annual mean, °C'],
  ['swe_mm_s', 'Snow water equivalent', 'mm', 1, 'annual mean, mm'],
  ['pds_ix_s', 'Palmer drought index', 'index', 1, 'annual mean'],
  ['soil_mm_s', 'Soil moisture', 'mm', 1, 'annual mean, mm'],
];
const SYSTEMS = [['amu_darya', 'Amu Darya'], ['syr_darya', 'Syr Darya']];

function VersionChart({ series, factor, label }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const rows = series.annual_mean.map(([year, old, fresh]) => ({ year, old: old * factor, fresh: fresh * factor }));
  const values = rows.flatMap(row => [row.old, row.fresh]);
  let low = Math.min(...values), high = Math.max(...values);
  if (low === high) { low -= 1; high += 1; }
  const height = 170, pad = { top: 10, right: 10, bottom: 22, left: 42 };
  const plot = Math.max(0, width - pad.left - pad.right), tall = height - pad.top - pad.bottom;
  const x = i => pad.left + (rows.length === 1 ? plot / 2 : (i / (rows.length - 1)) * plot);
  const y = v => pad.top + tall - ((v - low) / (high - low)) * tall;
  const path = key => rows.map((row, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(row[key]).toFixed(1)}`).join('');
  const picked = hover === null ? null : rows[hover];
  return <figure className="seas-chart">
    <div ref={ref}>{width > 0 && <svg width={width} height={height} role="img" aria-label={label}
      onPointerMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        const i = Math.round(((event.clientX - box.left - pad.left) / plot) * (rows.length - 1));
        setHover(i >= 0 && i < rows.length ? i : null);
      }} onPointerLeave={event => { if (event.pointerType === 'mouse') setHover(null); }}>
      {[high, (high + low) / 2, low].map((tick, i) => <g key={i}>
        <line x1={pad.left} x2={pad.left + plot} y1={y(tick)} y2={y(tick)} className="poi-chart-grid"/>
        <text x={pad.left - 5} y={y(tick) + 4} textAnchor="end" className="poi-chart-axis">{formatNumber(tick, 0)}</text>
      </g>)}
      {rows.filter((_, i) => i % 5 === 0).map(row => <text key={row.year} x={x(rows.indexOf(row))} y={height - 5}
        textAnchor="middle" className="poi-chart-axis">{row.year}</text>)}
      <path d={path('old')} className="seas-line-old"/>
      <path d={path('fresh')} className="seas-line-new"/>
      {picked && <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + tall} className="poi-chart-cursor"/>}
    </svg>}</div>
    <figcaption className="poi-chart-readout">{picked
      ? `${picked.year}: v1.0 ${formatNumber(picked.old, 1)} · v1.1 ${formatNumber(picked.fresh, 1)}`
      : label}</figcaption>
  </figure>;
}

/**
 * The release the whole record now stands on, and what changed with it. Normals,
 * anomalies and trends everywhere on the portal moved with this, so the change is
 * shown rather than only noted.
 */
export function VersionSection({ comparison }) {
  const [name, setName] = useState('pre_mm_s');
  const row = VERSION_ROWS.find(entry => entry[0] === name);
  return <>
    <div className="seas-controls" role="group" aria-label="Variable compared">
      {VERSION_ROWS.map(([id, label]) => <button key={id} type="button" aria-pressed={name === id}
        onClick={() => setName(id)}>{label}</button>)}
    </div>
    <ul className="poi-chart-legend"><li><i className="seas-key-old"/>TerraClimate v1.0 (Earth Engine, to 2024)</li>
      <li><i className="seas-key-new"/>TerraClimate v1.1 (producer, to 2025)</li></ul>
    <div className="seas-cards">{SYSTEMS.map(([system, label]) => {
      const series = comparison.series[name]?.[system];
      if (!series) return null;
      const change = (series.mean_v1_1 - series.mean_v1_0);
      const relative = Math.abs(series.mean_v1_0) > 1 ? ` (${change > 0 ? '+' : ''}${formatNumber(change / Math.abs(series.mean_v1_0) * 100, 1)}%)` : '';
      return <div key={system} className="seas-card">
        <h3>{label}</h3>
        <VersionChart series={series} factor={row[3]} label={`${row[1]}, ${row[4]}, ${series.years.join('–')}`}/>
        <p className="seas-meta">Mean {formatNumber(series.mean_v1_0, 2)} → {formatNumber(series.mean_v1_1, 2)} {row[2]}{relative};
          month-by-month correlation {formatNumber(series.correlation, 2)}.</p>
      </div>;
    })}</div>
  </>;
}
