import React, { useState } from 'react';
import { ArrowUpRight, Download, ArrowRight } from 'lucide-react';
const BASE = '/data/case-studies/';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmt = (x, digits = 1) => x == null ? '—' : Number(x).toLocaleString('en', { maximumFractionDigits: digits });
import Chart from './TimeSeriesChart.jsx';
export function StationEvidence({ data }) {
  const [station, setStation] = useState('uz:station/meteo-419704');
  const [variable, setVariable] = useState('precipitation_total');
  const info = data.inventory.find(r => r.station_id === station && r.variable === variable);
  if (!info) return <section className="cs-panel" id="station-evidence"><h2>Station evidence</h2><p>This station-variable combination has no published inventory.</p><button onClick={() => { setStation(data.inventory[0]?.station_id); setVariable(data.inventory[0]?.variable); }}>Select an available record</button></section>;
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
      : <p className="cs-note cs-pending">No eligible product comparison is published for this station and variable. Check temporal overlap and QA before interpreting this absence.</p>}
    <details><summary>Station provenance</summary><p>Station URI: {info.station_id}<br />Containing level-12 basin: {info.basin_id}<br />Source workbooks: {info.source_files.join('; ')}</p></details>
  </section>;
}

export function DischargeEvidence({ data }) {
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
    <p>Pskem–Mullala discharge provides the observed target for runoff modelling. The first test is a monthly climatology trained on <strong>{b.training}</strong> and evaluated on <strong>{b.evaluation}</strong>.</p>
    <Chart rows={rows} fields={fields} unit="m³/s" title="Pskem–Mullala discharge" />
    <div className="cs-score-grid">{[['n', 'Held-out months'], ['rmse', 'RMSE · m³/s'], ['nse', 'NSE'], ['kge', 'KGE (2009)']].map(([key, label]) => <div key={key}><strong>{fmt(b.scores[key], key === 'n' ? 0 : 3)}</strong><span>{label}</span></div>)}</div>
    <p className="cs-note">These scores evaluate the seasonal benchmark. The models below are compared with this same baseline. Bias = prediction − observation. <a href="https://hess.copernicus.org/articles/23/4323/2019/">NSE and KGE interpretation <ArrowUpRight size={12} /></a></p>
    <details><summary>Quality control, uncertainty and source sensitivity</summary>
      <p>{s.daily_discharge_rows.toLocaleString()} daily rows; {s.suspect_daily_rows} source-flagged values excluded from screened means. {s.invalid_calendar_rows} impossible calendar record quarantined (2015-02-29). Monthly means require 90% valid daily coverage. Volumes require every day; incomplete months are not extrapolated.</p>
      <div className="cs-table-wrap"><table><thead><tr><th>Score</th><th>Screened</th><th>95% year-block interval</th><th>Raw sensitivity</th></tr></thead><tbody>
        {['rmse', 'mae', 'bias', 'nse', 'kge'].map(key => <tr key={key}><td>{key.toUpperCase()}</td><td>{fmt(b.scores[key], 3)}</td><td>{b.uncertainty?.intervals[key]?.map(v => fmt(v, 3)).join(' to ') || 'Unavailable'}</td><td>{fmt(b.raw_sensitivity_scores[key], 3)}</td></tr>)}
      </tbody></table></div><p>{b.uncertainty?.method}. Only seven held-out years; these intervals do not include rating-curve uncertainty. {b.sensitivity_note}</p>
      <a href={`${BASE}discharge-audit.csv`} download>Download monthly audit <Download size={13} /></a> · <a href={`${BASE}discharge-rejected-dates.csv`} download>Rejected date records</a>
    </details>
  </section>;
}
