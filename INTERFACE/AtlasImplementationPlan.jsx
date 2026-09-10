import React, { useState } from 'react';
import './atlas-plan.css';

const number = (v, digits = 0) => Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
export default function AtlasImplementationPlan({ plan }) {
  const [variables, setVariables] = useState(10), [years, setYears] = useState(27);
  const [batchSize, setBatchSize] = useState(200), [batchMinutes, setBatchMinutes] = useState('');
  if (!plan) return null;
  const r = plan.runtime, batches = Math.ceil(r.domain_basins / batchSize);
  const estimate = batchMinutes !== '' && Number(batchMinutes) > 0 ? batches * Number(batchMinutes) / 60 : null;
  return <section id="implementation-plan" className="atlas-plan">
    <p className="eyebrow">IMPLEMENTATION PLAN · {plan.as_of}</p><h2>{plan.title}</h2>
    <p>{plan.scope}</p><p>{plan.recommendation}</p>
    <div className="plan-stages">{plan.stages.map(stage => <article key={stage.id} id={stage.id}>
      <div className="plan-stage-top"><span>{stage.number.toString().padStart(2, '0')}</span><small>{stage.status.replaceAll('_', ' ')}</small></div>
      <h3>{stage.title}</h3><p>{stage.description}</p>
      <details><summary>Deliverables &amp; acceptance gate</summary><ul>{stage.deliverables.map(d => <li key={d}>{d}</li>)}</ul><p><strong>Gate:</strong> {stage.gate}</p><p className="plan-evidence">Evidence: {stage.evidence.join(' · ')}</p></details>
    </article>)}</div>
    <div className="plan-storage"><h3>Store time now. Use it for research and ontology later.</h3><p>Keep a long observation table, with one basin / indicator / period / method / revision per record. Preserve observation time separately from retrieval and publication time. Basins and indicators connect to the ontology; large numeric time series remain in the data store.</p><p><strong>Stage 5 starts alongside stage 2.</strong> A historical normal, an annual map and a dated monthly observation are different record types. Preserve source-native resolution and the processing grid separately.</p><details><summary>Proposed observation and provenance contract</summary>{Object.entries(plan.storage_contract).filter(([key, value]) => Array.isArray(value) && key !== 'sources').map(([key, value]) => <p key={key}><strong>{key.replaceAll('_', ' ')}:</strong> {value.join(' · ')}</p>)}<p>{plan.storage_contract.physical_design}</p><p>{plan.storage_contract.ontology_mapping}</p><p><a href="https://www.w3.org/TR/vocab-ssn/">SOSA/SSN concepts</a> · <a href="https://www.w3.org/TR/prov-o/">PROV provenance</a></p></details></div>
    <h3>What will a regional update cost?</h3>
    <div className="batch-table-scroll"><table className="plan-timing"><thead><tr><th>Workload</th><th>Time / size</th><th>Evidence and meaning</th></tr></thead><tbody>
      <tr><td>20-basin cold pilot</td><td>{number(r.pilot_cold_seconds / 60, 2)} minutes</td><td>Measured fixed-period run, including source acquisition.</td></tr>
      <tr><td>20-basin warm pilot</td><td>{number(r.pilot_warm_seconds, 2)} seconds</td><td>Measured cached rerun; not an incremental monthly fetch.</td></tr>
      <tr><td>Regional acquisition</td><td>~{r.regional_acquisition_hours_extrapolated} hours</td><td>Linear extrapolation from cold pilot pixels; queueing/retries unmeasured.</td></tr>
      <tr><td>Regional current reduction</td><td>~{r.regional_current_reduction_hours_extrapolated} hours</td><td>Extrapolated inefficient per-basin raster scans.</td></tr>
      <tr><td>Grouped arithmetic kernel</td><td>~{r.regional_grouped_kernel_minutes} minutes</td><td>{r.regional_grouped_kernel_note}</td></tr>
      <tr><td>Regional cached rasters at 15″</td><td>~{r.raster_storage_15arcsec_gb} GB</td><td>Published projection for the current band inventory, excluding archives, revisions and overhead.</td></tr>
    </tbody></table></div>
    <p>{r.baseline_interpretation}</p><p>{r.incremental_interpretation}</p><p>{r.environmental_interpretation}</p>
    <p className="plan-evidence">Evidence: <a href="/data/atlas/surrogate-science.json">saved benchmark and assumptions</a> · run <code>{r.evidence_run_id}</code>. <a href={r.source}>Earth Engine batch-processing guidance</a>.</p>
    <div className="plan-calculators"><article><h3>Temporal table size</h3><p>Scenario for {number(r.domain_basins)} basins; only variables suitable for monthly observations belong here.</p><div className="plan-controls"><label>Monthly indicators<input type="number" min="1" max="281" value={variables} onChange={e => setVariables(Math.max(1, Math.min(281, Number(e.target.value) || 1)))}/></label><label>Years<input type="number" min="1" max="100" value={years} onChange={e => setYears(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}/></label></div><strong className="plan-total">{number(r.domain_basins * variables * 12 * years)} rows</strong><p>{number(r.domain_basins * variables)} rows per additional month, before revisions, methods and support variants. One current 196-substitute snapshot across the region is {number(r.domain_basins * 196)} values. These are storage scenarios, not fetched observations.</p></article>
      <article><h3>Calibrate the monthly runtime</h3><p>Enter a measured complete batch duration after the proposed regional benchmark. No measured monthly duration exists yet.</p><div className="plan-controls"><label>Basins per batch<input type="number" min="1" max="7445" value={batchSize} onChange={e => setBatchSize(Math.max(1, Math.min(7445, Number(e.target.value) || 1)))}/></label><label>Measured minutes per batch<input type="number" min="0.01" step="0.1" value={batchMinutes} placeholder="Not benchmarked" onChange={e => setBatchMinutes(e.target.value)}/></label></div><strong className="plan-total">{estimate == null ? 'Awaiting benchmark' : `~${number(estimate, 1)} hours`}</strong><p>{batches} serial batches for one defined source/period workload. Assumes equal batch cost; excludes retries, queue delays and final validation. Parallel scaling is not assumed.</p></article></div>
    <p><strong>Higher resolution:</strong> {r.storage_note} Finer native processing can improve area estimates without increasing the number of basin rows. It does not create a within-basin map in the attribute table.</p>
    <h3>Next implementation batches</h3><ol>{plan.next_batches.map(item => <li key={item}>{item}</li>)}</ol>
    <div className="plan-legend"><span>Light green: substitute value available</span><span>Outlined badge: future resolution opportunity</span><span>Uncoloured / pending: no published substitute</span></div>
    <p><a href="/dynamic-atlas.html">Inspect sources and actual pilot values →</a> · <a href="/data/atlas/implementation-plan.json" download>Download the implementation plan</a></p>
  </section>;
}
