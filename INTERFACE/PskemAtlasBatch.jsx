import React, { useEffect, useState } from 'react';

export default function PskemAtlasBatch() {
  const [data, setData] = useState(null);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [basin, setBasin] = useState('4121289400');
  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const response = await fetch('/data/atlas/batch-latest.json', { cache: 'no-store' });
        if (!response.ok) throw new Error(`Pskem batch request failed (${response.status})`);
        const next = await response.json();
        if (!Array.isArray(next.attributes) || next.attribute_count !== 281) throw new Error('Invalid Pskem batch');
        if (active) { setData(next); setError(''); }
        const status = await fetch('/data/atlas/batch-status.json', { cache: 'no-store' });
        if (status.ok && active) setProgress(await status.json());
      } catch (e) { if (active) setError(e.message); }
    }
    refresh(); const interval = setInterval(refresh, 5000);
    return () => { active = false; clearInterval(interval); };
  }, []);
  const rows = data?.attributes.filter(a => `${a.column} ${a.label} ${a.source_dataset}`.toLowerCase().includes(query.toLowerCase())
    && (filter === 'all' || (filter === 'computed' ? a.candidate_status === 'computed_candidate'
      : filter === 'pass' ? a.comparison?.pass : a.candidate_status === 'pending_original_inputs'))) || [];
  const number = value => value == null ? 'Missing' : Number(value).toLocaleString(undefined, { maximumFractionDigits: 6 });
  return <section id="pskem-all-attributes" aria-label="Pskem 281 attribute processing">
    <h2>Pskem: all 281 attributes</h2>
    {error && <p role="alert">{error}{data ? '. Showing the last successful batch.' : ''}</p>}
    {!data && !error && <p>Loading Pskem results…</p>}
    {progress?.status === 'running' && <p role="status">Processing {progress.active_stage?.name?.replaceAll('_', ' ')} · {progress.wall_seconds.toFixed(2)} s elapsed</p>}
    {data && <>
      <p>{data.scope_note}</p>
      <div className="metrics"><div><strong>{data.reference_records.toLocaleString()}</strong><span>original reference records</span></div>
        <div><strong>{data.candidate_attributes}</strong><span>attributes recalculated</span></div>
        <div><strong>{data.numerical_pass_attributes}</strong><span>pass numerical comparison for all 20 basins</span></div>
        <div><strong>{data.independently_reproduced}</strong><span>independently reproduced</span></div></div>
      <p>{data.status_note} {data.pending_attributes} attributes await original source preparation.</p>
      <p><strong>Full processing: {data.timing.wall_seconds.toFixed(3)} seconds wall time</strong> · {data.timing.cpu_seconds.toFixed(3)} seconds CPU. Shared input preparation is counted once.</p>
      <details><summary>Full processing stages and timing scope</summary><p>{data.timing.timing_note}</p>
        <div className="batch-table-scroll"><table><thead><tr><th>Stage</th><th>Wall seconds</th><th>CPU seconds</th><th>Status</th></tr></thead><tbody>{data.timing.stages.map(s => <tr key={s.name}><td>{s.name.replaceAll('_', ' ')}</td><td>{s.wall_seconds.toFixed(3)}</td><td>{s.cpu_seconds.toFixed(3)}</td><td>{s.status}</td></tr>)}</tbody></table></div>
      </details>
      <div className="downloads">{[['observations.csv', 'All basin observations'], ['reference-wide.csv', 'Original 281-column table'], ['attribute-audit.csv', 'Attribute readiness audit'], ['source-lock.json', 'Source hashes'], ['timing.json', 'Full timing report']].map(([file, label]) => <a key={file} href={data.download_base + file} download>{label} ↓</a>)}</div>
      <div className="filters"><label>Basin<select aria-label="Basin" value={basin} onChange={e => setBasin(e.target.value)}>{data.basin_ids.map(id => <option key={id}>{id}</option>)}</select></label>
        <label>Search<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Attribute or original source"/></label>
        <label>Readiness<select aria-label="Readiness" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All attributes</option><option value="computed">Recalculated candidates</option><option value="pass">Numerical comparison passed</option><option value="pending">Original inputs pending</option></select></label></div>
      <p>{rows.length} of 281 attributes · values below use the original stored units.</p>
      <div className="attributes">{rows.map(a => <details key={a.column}><summary><code>{a.column}</code><span>{a.label}</span><small>{a.comparison ? `${a.comparison.within_tolerance}/20 within tolerance` : 'Inputs pending'}</small></summary>
        <div className="recipe"><p><strong>Original reference: {number(a.reference_values[basin])}</strong> · Candidate: {a.candidate_values ? number(a.candidate_values[basin]?.raw_value) : 'Not computed'} · {a.units}</p>
          <p>Physical reference: {number(a.reference_values[basin] == null ? null : a.reference_values[basin] * a.physical_factor)} {a.physical_unit}. Spatial support: {a.spatial_support}. Original period: {a.reference_period}.</p>
          <p><a href={a.source_url} target="_blank" rel="noreferrer">{a.source_dataset}</a> · {a.source_citation}</p>
          {a.comparison && <p>Maximum absolute error: {number(a.comparison.max_absolute_error_raw)}; declared tolerance: {a.comparison.absolute_tolerance_raw} stored units. Calculation and comparison: {a.calculation_wall_seconds.toFixed(6)} s.</p>}
          <p>{a.review_required}</p><pre>{a.pseudocode}</pre></div>
      </details>)}</div>
      <small>Run {data.run_id} · checks for published processing updates every 5 seconds.</small>
    </>}
  </section>;
}
