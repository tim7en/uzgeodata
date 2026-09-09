import React from 'react';
import Chart from './TimeSeriesChart.jsx';
import usePublishedData from './usePublishedData.js';
const fmt=x=>x==null?'Unavailable':Number(x).toLocaleString('en',{maximumFractionDigits:3});

export default function ModelReview(){
  const {data,error,retry}=usePublishedData('/data/case-studies/model-review.json');
  if(error)return <section id="model-review" className="cs-panel" role="alert"><h2>Model re-evaluation unavailable</h2><p>{error}</p><button onClick={retry}>Retry review</button></section>;
  if(!data)return <section id="model-review" className="cs-panel" role="status">Loading the chronological model review…</section>;
  const monthly=data.monthly_rows.filter(r=>Number(r.period.slice(0,4))>=data.test_years[0]).map(r=>({...r,observed:r.split==='validation'?r.observed:null,simulated:r.split==='validation'?r.simulated:null,benchmark:r.split==='validation'?r.benchmark:null}));
  const seasons=data.seasonal_rows.filter(r=>r.period==='validation').map(r=>({...r,observed:r.observedMcm,simulated:r.simulatedMcm}));
  const fields=[{key:'observed',label:'Observed',color:'#58c9e5'},{key:'simulated',label:'Chronological model',color:'#edb06c'},{key:'benchmark',label:'Training-only climatology',color:'#baa5ef',dashed:true}];
  return <section id="model-review" className="cs-panel">
    <span className="cs-eyebrow">NEW RUN / CHRONOLOGICAL EVALUATION</span><h2>{data.candidate.seasonal.nse<=0?'Flow timing has skill. Seasonal volume remains uncertain.':'Historical runoff skill is not yet operational forecast validation.'}</h2>
    <p>Parameters were selected on {data.train_years[0]}–{data.train_years.at(-1)} and tested on {data.test_years[0]}–{data.test_years.at(-1)}. The search kept the existing physical bounds and optimized calibration KGE only. This test—not a collection of unrelated product figures—is the central runoff result.</p>
    <div className="cs-score-grid">{[['daily','Daily NSE'],['monthly','Monthly NSE'],['seasonal','Seasonal volume NSE']].map(([key,label])=><div key={key}><strong>{fmt(data.candidate[key].nse)}</strong><span>{label} · held-out years</span></div>)}<div><strong>{fmt(data.candidate.seasonal.pbias)}%</strong><span>Seasonal volume bias</span></div></div>
    <p className="cs-note">The earlier reference used a {data.reference.split} split (monthly NSE {fmt(data.reference.monthly.nse)}). Different test years mean these scores are not directly comparable. No additional tuning was selected using the new holdout.</p>
    <Chart rows={monthly} fields={fields} unit="mm/day" title="Does the model follow monthly river flow?"/>
    <Chart rows={seasons} fields={fields} unit="million m³" title="Does it reproduce April–September water volume?"/>
    <div className="cs-science-warning"><strong>What the seasonal result means</strong><p>Seasonal NSE is {fmt(data.candidate.seasonal.nse)}. {data.candidate.seasonal.nse<=0?'The model does not beat the held-out seasonal mean in squared-error terms.':'The model beats the held-out seasonal mean in squared-error terms.'} The training-only climatology baseline has seasonal NSE {fmt(data.benchmark.seasonal.nse)}. Neither comparison establishes reliable operational seasonal forecasting.</p><p>Using class thresholds learned only from calibration years, {data.classes.exact} of {data.classes.test_years} seasons match the observed class; {data.classes.within_one} fall within one class. These few retrospective years are not operational validation.</p></div>
    <div className="cs-table-wrap"><table><thead><tr><th>Held-out target</th><th>Pairs</th><th>Model NSE</th><th>Climatology NSE</th><th>Model bias (%)</th></tr></thead><tbody>{[['daily','Daily flow'],['monthly','Monthly mean flow'],['seasonal','Seasonal volume']].map(([key,label])=><tr key={key}><td>{label}</td><td>{data.candidate[key].n}</td><td>{fmt(data.candidate[key].nse)}</td><td>{fmt(data.benchmark[key].nse)}</td><td>{fmt(data.candidate[key].pbias)}</td></tr>)}</tbody></table></div>
    <details><summary>Parameter search, coverage and limitations</summary><p>{data.decision}</p><ul>{data.limitations.map(text=><li key={text}>{text}</li>)}</ul>
      <div className="cs-table-wrap"><table><thead><tr><th>Parameter</th><th>Selected value</th><th>Bounds</th><th>Diagnostic</th></tr></thead><tbody>{Object.entries(data.model.parameters).map(([key,value])=><tr key={key}><td>{key}</td><td>{fmt(value)}</td><td>{data.model.parameterBounds[key].map(fmt).join(' to ')}</td><td>{data.parameters_at_bounds.includes(key)?'At bound — review forcing/structure':'Within bounds'}</td></tr>)}</tbody></table></div>
      <p>Paired days in each April–September season: {seasons.map(r=>`${r.year}: ${r.valid_days}/${r.expected_days}`).join('; ')}. Volumes are not extrapolated to missing days.</p>
    </details>
    <div className="cs-download-links"><a href="/data/case-studies/model-review.json" download>Review, chart data and source hashes · JSON</a><a href={data.run_directory+'pskem-daily-model.csv'} download>New daily run · CSV</a><a href={data.run_directory+'pskem-daily-model.json'} download>New parameters and scores · JSON</a></div>
  </section>;
}
