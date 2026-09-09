import React, {useState} from 'react';
import Chart from './TimeSeriesChart.jsx';
import usePublishedData from './usePublishedData.js';

const BASE='/data/case-studies/';
const fmt=x=>x == null ? 'Unavailable' : x.toLocaleString('en',{maximumFractionDigits:3});

export default function CurrentModel() {
  const {data,error,retry}=usePublishedData(BASE+'current-model.json');
  const [view,setView]=useState('monthly'), [split,setSplit]=useState('validation');
  if(error) return <section id="current-model" className="cs-panel" role="alert"><h2>Current model evidence unavailable</h2><p>{error}</p><button onClick={retry}>Retry model data</button></section>;
  if(!data) return <section id="current-model" className="cs-panel" role="status">Loading current model results…</section>;
  const rows=view==='monthly' ? data.monthly_rows.map(r=>({...r,observed:r.split===split?r.observed:null,simulated:r.split===split?r.simulated:null}))
    : data.seasonal_rows.map(r=>({...r,observed:(data[split+'_years']||[]).includes(r.year)?r.observedMcm:null,simulated:(data[split+'_years']||[]).includes(r.year)?r.simulatedMcm:null}));
  const revision=data.source_hashes['pskem-daily-model.json'].slice(0,12);
  return <section id="current-model" className="cs-panel">
    <span className="cs-eyebrow">CURRENT PROCESS MODEL / {data.model.timestep.toUpperCase()} TIMESTEP</span>
    <h2>Snow storage, soil water and river flow.</h2><p>{data.model.family}. Elevation-dependent temperature and snowmelt feed soil storage and fast/slow runoff pathways.</p>
    <div className="cs-score-grid">{[[data.daily.nse,'Daily NSE'],[data.monthly.nse,'Monthly NSE'],[data.seasonal.nse,'April–September volume NSE'],[data.daily.pbias,'Daily bias (%)']].map(([v,label])=><div key={label}><strong>{fmt(v)}</strong><span>{label} · validation</span></div>)}</div>
    <p className="cs-note">{data.daily.n.toLocaleString()} paired validation days · {data.monthly.n} months · {data.validation_years.length} held-out years. Fit generated {data.model_generated_at.slice(0,10)}; charts rebuilt {data.generated_at.slice(0,10)}. Values are checked against the daily output before publication.</p>
    <div className="cs-controls"><label>Current model chart<select aria-label="Current model chart" value={view} onChange={e=>setView(e.target.value)}><option value="monthly">Monthly mean runoff</option><option value="seasonal">April–September water volume</option></select></label><label>Evaluation split<select aria-label="Evaluation split" value={split} onChange={e=>setSplit(e.target.value)}><option value="validation">Held-out years</option><option value="calibration">Calibration years</option></select></label></div>
    <Chart rows={rows} fields={[{key:'observed',label:'Observed',color:'#58c9e5'},{key:'simulated',label:'Current model',color:'#edb06c'}]} title={`${view==='monthly'?'Monthly runoff':'Seasonal volume'} · ${split}`} unit={view==='monthly'?'mm/day':'million m³'}/>
    <p className="cs-note">{data.monthly_support} Gaps separate years outside the selected split.</p>
    {view==='seasonal' && <p className="cs-note">Seasonal volumes integrate the available paired days in the source model; missing days are not extrapolated. Review day coverage below before interpreting a seasonal total.</p>}
    <div className="cs-science-warning"><strong>Historical skill, not an operational forecast</strong><p>{data.scope}</p><p>{data.catchment.caveat}</p></div>
    <details><summary>Regenerated model figures and evaluation details</summary><p>Validation years: {data.validation_years.join(', ')}. Calibration years: {data.calibration_years.join(', ')}. Objective: {data.model.calibration.objective}; split: {data.model.calibration.split}. Parameters and bounds remain in the model download.</p>
      <div className="cs-table-wrap"><table><thead><tr><th>Season</th><th>Paired days</th><th>Calendar days</th></tr></thead><tbody>{data.seasonal_rows.map(r=><tr key={r.year}><td>{r.year}</td><td>{r.valid_days}</td><td>{r.expected_days}</td></tr>)}</tbody></table></div>
      <div className="cs-model-figures">{[['pskem-daily-hydrograph.png','Daily runoff and modelled snow-water storage'],['pskem-monthly-skill.png','Monthly observed versus modelled runoff'],['pskem-seasonal-shape.png','Mean seasonal pattern in held-out years']].map(([file,label])=><a href={`${BASE}${file}?v=${revision}`} key={file}><img src={`${BASE}${file}?v=${revision}`} alt={label} loading="lazy"/><span>{label}</span></a>)}</div>
    </details><div className="cs-download-links"><a href={BASE+'current-model.json'} download>Chart values, scores and source hashes · JSON</a><a href={BASE+'pskem-daily-model.csv'} download>Daily simulation and observations · CSV</a><a href={BASE+'pskem-daily-model.json'} download>Parameters and full model results · JSON</a></div>
  </section>;
}
