import React, { useEffect, useState } from 'react';
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip } from 'react-leaflet';
import { ArrowUpRight, Download, Droplets, ArrowRight } from 'lucide-react';

const BASE = '/data/case-studies/';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmt = (x, digits = 1) => x == null ? '—' : Number(x).toLocaleString('en', { maximumFractionDigits: digits });
const fetchJSON = async url => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load case-study evidence (${response.status}).`);
  return response.json();
};

function Chart({ rows, fields, unit, title }) {
  const [hover, setHover] = useState(null);
  const width = 760, height = 260, left = 58, right = 22, top = 22, bottom = 42;
  const values = rows.flatMap(r => fields.map(f => r[f.key])).filter(v => v != null && Number.isFinite(v));
  if (!values.length) return <p>No eligible values for this selection.</p>;
  const min = Math.min(0, ...values), max = Math.max(...values, min + 1) * 1.08;
  const x = i => left + i / Math.max(1, rows.length - 1) * (width - left - right);
  const y = v => top + (max - v) / (max - min) * (height - top - bottom);
  const segments = key => {
    let path = '', active = false;
    rows.forEach((r, i) => {
      if (r[key] == null) { active = false; return; }
      path += `${active ? 'L' : 'M'}${x(i)},${y(r[key])} `;
      active = true;
    });
    return path;
  };
  const ticks = [...new Set([0, Math.floor((rows.length - 1) / 4), Math.floor((rows.length - 1) / 2), Math.floor((rows.length - 1) * 3 / 4), rows.length - 1])];
  const selected = hover == null ? null : rows[hover];
  return <figure className="cs-chart">
    <figcaption>{title} <span>{unit}</span></figcaption>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title}, ${unit}. Exact values are available in the data table below.`}
      onMouseLeave={() => setHover(null)} onMouseMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        const px = (event.clientX - box.left) / box.width * width;
        setHover(Math.max(0, Math.min(rows.length - 1, Math.round((px - left) / (width - left - right) * (rows.length - 1)))));
      }}>
      {[0, 1, 2, 3, 4].map(i => {
        const value = min + (max - min) * i / 4;
        return <g key={i}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="cs-grid" />
          <text x={left - 10} y={y(value) + 4} textAnchor="end">{fmt(value, 0)}</text></g>;
      })}
      {ticks.map(i => <text key={i} x={x(i)} y={height - 13} textAnchor="middle">{rows[i].label || rows[i].period}</text>)}
      {fields.map(field => <path key={field.key} d={segments(field.key)} fill="none" stroke={field.color} strokeWidth="2.4" strokeDasharray={field.dashed ? '6 4' : undefined} />)}
      {hover != null && <line x1={x(hover)} x2={x(hover)} y1={top} y2={height - bottom} className="cs-cursor" />}
    </svg>
    <div className="cs-legend">{fields.map(f => <span key={f.key}><i style={{ background: f.color }} />{f.label}</span>)}</div>
    <div className="cs-readout">{selected ? <>{selected.label || selected.period} · {fields.map(f => `${f.label}: ${fmt(selected[f.key], 2)} ${unit}`).join(' · ')}</> : 'Move across the chart to inspect values. Gaps remain visible.'}</div>
    <details><summary>View exact chart data</summary><div className="cs-table-wrap"><table><thead><tr><th>Period</th>{fields.map(f => <th key={f.key}>{f.label} ({unit})</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}><td>{r.label || r.period}</td>{fields.map(f => <td key={f.key}>{fmt(r[f.key], 3)}</td>)}</tr>)}</tbody></table></div></details>
  </figure>;
}

function StationEvidence({ data }) {
  const [station, setStation] = useState('uz:station/meteo-419704');
  const [variable, setVariable] = useState('precipitation_total');
  const info = data.inventory.find(r => r.station_id === station && r.variable === variable);
  const rows = data.station_series.filter(r => r.station_id === station && r.variable === variable);
  const comparisons = data.validation.comparisons.filter(r => r.station_id === station && r.variable === variable && r.season === 'all');
  const products = [...new Set(comparisons.map(r => r.product))];
  const productPairs = data.validation.pairs.filter(r => r.station_id === station && r.variable === variable);
  const chartRows = rows.map(r => ({ ...r, ...Object.fromEntries(products.map(product => [product, productPairs.find(p => p.product === product && p.period === r.period)?.predicted ?? null])) }));
  const fields = [{ key: 'value', label: 'Station observation', color: variable === 'precipitation_total' ? '#58c9e5' : '#edb06c' },
    ...products.map((p, i) => ({ key: p, label: p, color: ['#baa5ef', '#a9cd7e'][i % 2], dashed: true }))];
  return <section className="cs-panel" id="station-evidence">
    <div className="cs-section-head"><div><span className="cs-eyebrow">01 / THE OBSERVED RECORD</span><h2>Start with the stations.</h2></div>
      <div className="cs-controls"><label>Station<select aria-label="Station" value={station} onChange={e => setStation(e.target.value)}>
        {[...new Map(data.inventory.map(r => [r.station_id, r.station])).entries()].map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label>Variable<select aria-label="Variable" value={variable} onChange={e => setVariable(e.target.value)}><option value="precipitation_total">Precipitation</option><option value="air_temperature_mean">Air temperature</option></select></label></div>
    </div>
    <Chart rows={chartRows} fields={fields} unit={info.unit} title={`${info.station} · monthly ${variable === 'precipitation_total' ? 'precipitation total' : 'mean air temperature'}`} />
    <div className="cs-evidence-strip"><span><strong>{info.months}/{info.expected_months}</strong> observed months</span><span><strong>{info.start} → {info.end}</strong> observation window</span><span><strong>{info.missing.length || 'No'}</strong> missing months</span></div>
    {info.missing.length > 0 && <p className="cs-note">Missing: {info.missing.join(', ')}. Values are not interpolated.</p>}
    {comparisons.length ? <div className="cs-table-wrap"><table><thead><tr><th>Raw product</th><th>Pairs</th><th>RMSE ({info.unit})</th><th>Bias ({info.unit})</th><th>r</th></tr></thead>
      <tbody>{comparisons.map(r => <tr key={r.product}><td>{r.product}</td><td>{r.scores.n}</td><td>{fmt(r.scores.rmse, 2)}</td><td>{fmt(r.scores.bias, 2)}</td><td>{fmt(r.scores.r, 3)}</td></tr>)}</tbody></table></div>
      : <p className="cs-note cs-pending">Product validation is pending historical station-cell extraction. The stored 2025–2026 basin series do not overlap these observations.</p>}
    <details><summary>Station provenance</summary><p>Station URI: {info.station_id}<br />Containing level-12 basin: {info.basin_id}<br />Source workbooks: {info.source_files.join('; ')}</p></details>
  </section>;
}

function DischargeEvidence({ data }) {
  const [mode, setMode] = useState('series');
  const { benchmark: b, summary: s } = data;
  const rows = mode === 'series' ? data.discharge_monthly.map(r => ({ ...r, screened_mean: r.eligible ? r.screened_mean : null }))
    : data.discharge_climatology.map(r => ({ label: MONTHS[r.month - 1], screened_mean: r.mean }));
  const fields = [{ key: 'screened_mean', label: mode === 'series' ? 'Screened observation' : 'Observed climatology', color: '#58c9e5' }];
  if (mode === 'series') fields.push({ key: 'benchmark', label: 'Held-out seasonal benchmark', color: '#edb06c', dashed: true });
  return <section className="cs-panel" id="discharge-evidence">
    <div className="cs-section-head"><div><span className="cs-eyebrow">02 / THE HYDROLOGICAL TEST</span><h2>A benchmark before a model.</h2></div>
      <div className="cs-switch" aria-label="Discharge chart view">{[['series', 'Time series'], ['season', 'Seasonal cycle']].map(([value, label]) => <button key={value} aria-pressed={mode === value} onClick={() => setMode(value)}>{label}</button>)}</div>
    </div>
    <p>Pskem–Mullala discharge provides an independent target for future runoff modelling. The first test is a monthly climatology trained on <strong>{b.training}</strong> and evaluated on <strong>{b.evaluation}</strong>.</p>
    <Chart rows={rows} fields={fields} unit="m³/s" title="Pskem–Mullala discharge" />
    <div className="cs-score-grid">{[['n', 'Held-out months'], ['rmse', 'RMSE · m³/s'], ['nse', 'NSE'], ['kge', 'KGE (2009)']].map(([key, label]) => <div key={key}><strong>{fmt(b.scores[key], key === 'n' ? 0 : 3)}</strong><span>{label}</span></div>)}</div>
    <p className="cs-note">These scores evaluate the seasonal benchmark. A future snow/runoff model must improve on it. Bias = prediction − observation. <a href="https://hess.copernicus.org/articles/23/4323/2019/">NSE and KGE interpretation <ArrowUpRight size={12} /></a></p>
    <details><summary>Quality control, uncertainty and source sensitivity</summary>
      <p>{s.daily_discharge_rows.toLocaleString()} daily rows; {s.suspect_daily_rows} source-flagged values excluded from screened means. {s.invalid_calendar_rows} impossible calendar record quarantined (2015-02-29). Monthly means require 90% valid daily coverage. Volumes require every day; incomplete months are not extrapolated.</p>
      <div className="cs-table-wrap"><table><thead><tr><th>Score</th><th>Screened</th><th>95% year-block interval</th><th>Raw sensitivity</th></tr></thead><tbody>
        {['rmse', 'mae', 'bias', 'nse', 'kge'].map(key => <tr key={key}><td>{key.toUpperCase()}</td><td>{fmt(b.scores[key], 3)}</td><td>{b.uncertainty?.intervals[key]?.map(v => fmt(v, 3)).join(' to ') || 'Unavailable'}</td><td>{fmt(b.raw_sensitivity_scores[key], 3)}</td></tr>)}
      </tbody></table></div><p>{b.uncertainty?.method}. Only seven held-out years; these intervals do not include rating-curve uncertainty. {b.sensitivity_note}</p>
      <a href={`${BASE}discharge-audit.csv`} download>Download monthly audit <Download size={13} /></a> · <a href={`${BASE}discharge-rejected-dates.csv`} download>Rejected date records</a>
    </details>
  </section>;
}

function StudyPortfolio({ data }) {
  const [selected, setSelected] = useState(data.studies[0].id);
  const study = data.studies.find(r => r.id === selected);
  return <section id="portfolio" className="cs-portfolio">
    <div className="cs-section-head"><div><span className="cs-eyebrow">03 / THE RESEARCH PROGRAMME</span><h2>Six connected case studies.</h2></div><p>Each starts with a testable question<br />and ends with an evidence threshold.</p></div>
    <div className="cs-study-layout"><nav className="cs-study-nav" aria-label="Choose a case study">{data.studies.map((r, i) => <button key={r.id} aria-pressed={selected === r.id} onClick={() => setSelected(r.id)}>
      <span>0{i + 1}</span><div><strong>{r.theme}</strong><small>{r.status}</small></div><ArrowRight size={16} /></button>)}</nav>
      <article className="cs-study"><span className="cs-status">{study.status}</span><h3>{study.title}</h3><p className="cs-question">{study.question}</p>
        <div className="cs-hypothesis"><span className="cs-eyebrow">HYPOTHESIS</span><p>{study.hypothesis}</p></div>
        <h4>Observation base</h4><p>{study.observations}</p>
        <h4>Study protocol</h4><ol>{study.method.map(step => <li key={step}>{step}</li>)}</ol>
        <div className="cs-study-columns"><div><h4>Evaluation</h4><ul>{study.metrics.map(v => <li key={v}>{v}</li>)}</ul></div><div><h4>Deliverables</h4><ul>{study.deliverables.map(v => <li key={v}>{v}</li>)}</ul></div></div>
        <div className="cs-gates"><h4>Evidence needed before stronger claims</h4>{study.gates.map(v => <p key={v}>{v}</p>)}</div>
        <h4>Decision supported</h4><p>{study.decision}</p>
        <div className="cs-sources">{data.sources.filter(r => study.sources.includes(r.id)).map(r => <a key={r.id} href={r.url}>{r.title} <ArrowUpRight size={12} /></a>)}</div>
      </article></div>
  </section>;
}

export default function CaseStudies() {
  const [data, setData] = useState(null), [geometry, setGeometry] = useState(null), [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    Promise.all([fetchJSON(`${BASE}chirchik.json`), fetchJSON(`${BASE}pskem-candidate-catchment.geojson`)])
      .then(([d, g]) => { if (active) { setData(d); setGeometry(g); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  if (error) return <main className="cs-loading" role="alert"><h1>Case-study evidence could not be loaded.</h1><p>{error}</p><a href="/">Return to UzGeoData</a></main>;
  if (!data) return <main className="cs-loading" role="status">Loading the Chirchik evidence record…</main>;
  const { summary: s, catchment: c } = data;
  const stations = [...new Map(data.inventory.map(r => [r.station_id, r])).values()];
  return <div className="cs-app">
    <header className="cs-header"><a className="cs-logo" href="/"><Droplets size={22} /> UZGEODATA <span>/ FIELD STUDIES</span></a><nav><a href="/climate.html">Climate</a><a href="/hydrography.html">Hydrography</a><a href={`${BASE}chirchik-report.md`} download><Download size={14} /> Study report</a></nav></header>
    <main>
      <section className="cs-hero"><div><span className="cs-eyebrow">CHIRCHIK–CHARVAK / WESTERN TIAN SHAN</span><h1>Follow the water.<br /><em>Test the evidence.</em></h1><p>A basin observatory grounded in precipitation, temperature and river discharge. Six case studies connect mountain water formation to Charvak and downstream supply.</p>
        <div className="cs-hero-actions"><a className="cs-primary" href="#portfolio">Explore the case studies <ArrowRight size={16} /></a><a href="#station-evidence">Inspect the observations ↓</a></div></div>
        <aside className="cs-scope"><span className="cs-eyebrow">THE STARTING POINT</span><h2>Pskem first.</h2><p>{data.scope}</p><div><strong>{s.joint_months}</strong><span>joint climate–flow months<br />{s.joint_start} to {s.joint_end}</span></div><p className="cs-note">Observed-data analysis is available. Historical product validation and process attribution have separate evidence requirements.</p></aside>
      </section>
      <div className="cs-top-stats"><div><strong>3</strong><span>Meteorological stations</span></div><div><strong>2001–2017</strong><span>Pskem discharge record</span></div><div><strong>2010–2024</strong><span>Pskem climate record</span></div><div><strong>6</strong><span>Documented study protocols</span></div></div>
      <section className="cs-spatial cs-panel"><div><span className="cs-eyebrow">SPATIAL SCOPE</span><h2>The upstream network matters.</h2><p>The candidate gauge trace contains <strong>{c.basin_count} level-12 units</strong>, totalling <strong>{fmt(c.area_km2)} km²</strong>. All upstream units are retained across national boundaries.</p><p className="cs-note">{c.limitation}</p><p className="cs-note">All four stations are outside the existing headwater-pilot selection. This study requires a separately reviewed Pskem domain.</p><a href={`${BASE}pskem-candidate-catchment.geojson`} download>Download candidate catchment <Download size={13} /></a></div>
        <div className="cs-map"><MapContainer center={[41.95, 70.55]} zoom={8} scrollWheelZoom={false} aria-label="Candidate Pskem catchment and observation stations"><TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" attribution='&copy; OpenStreetMap contributors &copy; CARTO' /><GeoJSON data={geometry} style={{ color: '#167d97', weight: 1, fillColor: '#48adc5', fillOpacity: 0.23 }} />
          {stations.map(r => <CircleMarker key={r.station_id} center={[r.latitude, r.longitude]} radius={6} pathOptions={{ color: '#754617', fillColor: '#edb06c', fillOpacity: 1 }}><Tooltip>{r.station} meteorological station</Tooltip></CircleMarker>)}
          <CircleMarker center={[c.gauge_latitude, c.gauge_longitude]} radius={7} pathOptions={{ color: '#084e68', fillColor: '#49cfe9', fillOpacity: 1 }}><Tooltip>Pskem–Mullala gauge · coordinate requires reach review</Tooltip></CircleMarker>
        </MapContainer><span className="cs-map-label">Candidate trace · not a reviewed gauge boundary</span></div>
      </section>
      <StationEvidence data={data} /><DischargeEvidence data={data} /><StudyPortfolio data={data} />
      <section className="cs-downloads cs-panel"><div><span className="cs-eyebrow">04 / REPRODUCIBLE EVIDENCE</span><h2>Take the analysis with you.</h2><p>Existing station URIs, basin identifiers, source hashes and processing rules travel with the results.</p></div><div>{[['chirchik-report.md', 'Full case-study report'], ['pskem-observation-evidence.pdf', 'Observation figure · vector PDF'], ['pskem-observation-evidence.png', 'Observation figure · PNG'], ['chirchik.json', 'All results & protocols · JSON'], ['chirchik.manifest.json', 'Source hashes & QC policy'], ['discharge-audit.csv', 'Discharge quality audit · CSV'], ['station-annual.csv', 'Complete-year climate summaries · CSV'], ['joint-climate-discharge.csv', 'Matched climate–flow months · CSV']].map(([file, label]) => <a key={file} href={BASE + file} download>{label}<Download size={15} /></a>)}</div></section>
    </main><footer>UZGEODATA / CHIRCHIK CASE STUDIES <span>Analysis v{data.version} · Built {data.generated_at.slice(0, 10)} · Observations retain their original dates</span></footer>
  </div>;
}
