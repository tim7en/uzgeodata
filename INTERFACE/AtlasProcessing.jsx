import React, { useEffect, useState } from 'react';

const seconds = value => Number.isFinite(value) ? `${value.toFixed(3)} s` : '—';
const stageLabel = name => name.replaceAll('_', ' ');

export default function AtlasProcessing() {
  const [progress, setProgress] = useState(null);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const results = await Promise.all(['processing-status.json', 'latest-run.json', 'run-history.json'].map(async name => {
          const response = await fetch(`/data/atlas/${name}`, { cache: 'no-store' });
          if (response.status === 404) return null;
          if (!response.ok) throw new Error(`Processing status request failed (${response.status})`);
          return response.json();
        }));
        if (active) { setProgress(results[0]); setReport(results[1]); setHistory(results[2]); setError(''); }
      } catch (e) { if (active) setError(e.message); }
    }
    refresh(); const interval = setInterval(refresh, 5000);
    return () => { active = false; clearInterval(interval); };
  }, []);
  if (!progress && !report && !error) return null;
  return <section className="processing" aria-label="Pilot attribute processing">
    <div className="section-heading"><h2>One attribute. One pilot.</h2><span>Processing feed checks every 5 seconds</span></div>
    <p>Pskem candidate catchment · 20 level-12 units · <code>ele_mt_sav</code> — mean elevation</p>
    {error && <p role="alert">{error}. Showing the last available processing record.</p>}
    {progress && <>
      <div className="processing-summary"><div><strong>{seconds(progress.wall_seconds)}</strong><span>{progress.status === 'running' ? 'Elapsed at last update' : 'Latest attempt · full processing time'}</span></div><div><strong>{progress.status}</strong><span>{progress.active_stage ? stageLabel(progress.active_stage.name) : 'Execution status; scientific assessment below'}</span></div></div>
      <p className="processing-stamp">Run: <code>{progress.run_id}</code><br/>Started {progress.started_at} · Updated {progress.updated_at}</p>
      <div className="timing-table"><table><thead><tr><th>Processing stage</th><th>Wall time</th><th>CPU time</th></tr></thead><tbody>{progress.stages.map(stage => <tr key={stage.name}><td>{stageLabel(stage.name)}{stage.shared && <small> · shared preparation</small>}</td><td>{seconds(stage.wall_seconds)}</td><td>{seconds(stage.cpu_seconds)}</td></tr>)}{progress.status !== 'running' && <tr><td>Orchestration overhead</td><td>{seconds(progress.overhead_seconds)}</td><td>Included in total</td></tr>}</tbody><tfoot><tr><th>Full run</th><th>{seconds(progress.wall_seconds)}</th><th>{seconds(progress.cpu_seconds)}</th></tr></tfoot></table></div>
      <small>Wall time includes source transfer or cache verification, preparation, calculation, comparison and run-package export. CPU time covers the main Python process. Development, research, tests and web publication are separate.</small>
      {progress.active_stage && <p role="status">Latest event: {progress.events.at(-1)?.message}</p>}
    </>}
    {report && <div className="processing-result">
      <h3>Latest completed comparison{progress?.run_id !== report.run_id ? ' (earlier run)' : ''}</h3>
      <p><strong>{report.metrics.within_tolerance}/{report.basin_count} units within {report.metrics.absolute_tolerance_m} m.</strong> Mean absolute difference: {report.metrics.mae_m?.toFixed(3)} m. Largest difference: {report.metrics.max_absolute_error_m?.toFixed(3)} m.</p>
      <p>{report.numerical_gate_pass ? 'Numerical comparison passed.' : 'Numerical comparison needs investigation.'} Implementation is recorded; independent scientific reproduction remains pending.</p>
      <div className="downloads"><a href={report.observations_url} download>All pilot values and differences ↓</a><a href={report.timing_url} download>Full timing record ↓</a><a href={report.report_url} download>Comparison and limitations ↓</a><a href={report.manifest_url} download>Run manifest ↓</a><a href={report.source_lock_url} download>Source lock ↓</a></div>
    </div>}
    {history && <details className="attempts"><summary>All processing attempts · {seconds(history.recorded_wall_seconds)} recorded</summary><p>{history.note}</p>{history.runs.map(run => <p key={run.run_id}><code>{run.run_id}</code> · {run.status} · {seconds(run.wall_seconds)}{run.status === 'failed' && <><br/>{run.events.at(-1)?.message}</>}</p>)}</details>}
  </section>;
}
