import React, { useEffect, useState } from 'react';

const number = value => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
async function json(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw Error(`Substitute data could not be loaded (${response.status}).`);
  return response.json();
}

export function substituteRows(definitions, basinData, filter = '', kind = 'all') {
  const term = filter.trim().toLowerCase();
  return definitions.attributes.filter(a => {
    const upstream = ['u', 'p'].includes(a.support);
    return (kind === 'all' || (kind === 'basin_accumulation' ? upstream : !upstream))
      && `${a.column} ${a.label} ${a.category} ${definitions.families[a.family].source.name}`.toLowerCase().includes(term);
  }).map(a => ({ ...a, ...basinData.values[a.column], familyData: definitions.families[a.family] }));
}

export default function BasinSubstitutes({ basin, filter, kind }) {
  const [state, setState] = useState({ loading: true }), [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true;
    setState({ loading: true });
    (async () => {
      const index = await json('/data/atlas/substitutes-index.json');
      if (Number(basin.basin_level) !== index.basin_level || !index.basin_ids.includes(String(basin.hybas_id))) {
        if (live) setState({ index, absent: true });
        return;
      }
      const [definitions, values] = await Promise.all([
        json(`${index.base_url}definitions.json`), json(`${index.base_url}${basin.hybas_id}.json`),
      ]);
      if (definitions.run_id !== index.run_id || values.run_id !== index.run_id
        || String(values.hybas_id) !== String(basin.hybas_id) || values.basin_level !== Number(basin.basin_level)) {
        throw Error('Substitute basin or run does not match the selected basin. Refresh the data.');
      }
      if (live) setState({ index, definitions, values });
    })().catch(error => { if (live) setState({ error: error.message }); });
    return () => { live = false; };
  }, [basin.hybas_id, basin.basin_level, retry]);
  if (state.loading) return <p role="status" className="land-group-note">Loading this basin’s substitutes…</p>;
  if (state.error) return <div className="land-sub-note" role="alert"><p>{state.error}</p><button onClick={() => setRetry(n => n + 1)}>Retry substitutes</button></div>;
  if (state.absent) return <div className="land-sub-note"><h3>No substitutes published for this basin yet.</h3><p>The current run covers {state.index.basin_ids.length} Pskem level-12 units. Regional basins and coarser levels remain pending. Pilot values are not copied to other basins or summed into parent units.</p><a href="/roadmap.html#implementation-plan">Regional rollout plan →</a></div>;
  const rows = substituteRows(state.definitions, state.values, filter, kind);
  const available = rows.filter(row => row.value != null).length;
  return <>
    <div className="land-sub-note"><p><span className="land-sub-key">Light green: substitute available</span> {available} populated substitutes among {rows.length} matching attributes.</p><p>A substitute may use a fixed historical epoch or climatology. Green does not mean a newer observation or validated improvement. Outlined badges flag future spatial/temporal research opportunities.</p><p>Run <code>{state.index.run_id}</code> · <a href="/dynamic-atlas.html">Methods &amp; resolutions</a> · <a href={`${state.index.base_url}${basin.hybas_id}.json`} download>Download basin results</a></p></div>
    <table className="land-sub-table"><thead><tr><th>Attribute / status</th><th>Substitute value</th><th>Original / comparison</th><th>Period &amp; support</th><th>Resolution &amp; future work</th><th>Source &amp; evidence</th></tr></thead><tbody>
      {rows.map(row => {
        const f = row.familyData, r = f.resolution, filled = row.value != null;
        const converted = filled && f.units.convertible ? row.value * f.units.factor : null;
        return <tr key={row.column} data-substitute-status={filled ? 'available' : 'pending'}>
          <td><strong>{row.label}</strong><code>{row.column}</code><small>{filled ? 'Substitute available' : row.candidate_available ? 'Candidate exists; no substitute' : 'Pending substitute'}</small></td>
          <td className={filled ? 'land-sub-updated' : ''}><strong>{number(row.value)}</strong>{filled && <small>{f.units.surrogate}</small>}{!filled && <small>{row.pending_reason}</small>}</td>
          <td>{number(row.reference_raw)} <small>{f.units.reference_stored}</small>{filled && <small>{converted != null ? `Substitute in stored units: ${number(converted)}` : 'Different units; direct comparison unavailable'}</small>}</td>
          <td>{filled ? f.used_period : 'Not computed'}<small>{['u', 'p'].includes(row.support) ? 'Upstream support' : 'This sub-basin'} · {row.support}</small>{row.coverage != null && <small>{number(row.coverage * 100)}% spatial coverage; temporal QA separate</small>}</td>
          <td>{r.grid}<small>{r.native_scale_m ? `${number(r.native_scale_m)} m native · ` : ''}{r.processing_grid_arcsec}″ processing grid</small>
            {f.opportunities.spatial && <span className="land-opportunity" title={f.opportunities.spatial}>Spatial opportunity</span>}
            {f.opportunities.temporal && <span className="land-opportunity" title={f.opportunities.temporal}>Temporal opportunity</span>}
            {(f.opportunities.spatial || f.opportunities.temporal) && <details><summary>Future work</summary><p>{f.opportunities.spatial}</p><p>{f.opportunities.temporal}</p></details>}</td>
          <td><a href={f.source.catalogue_url} target="_blank" rel="noreferrer">{f.source.name}</a><small>{f.fidelity.replaceAll('_', ' ')}</small><small>{f.source.licence}</small><small>Retrieved: {f.retrieved_at || 'not recorded at source-lock level'}</small></td>
        </tr>;
      })}
    </tbody></table>
    {!rows.length && <p className="land-group-note">Nothing matches that filter.</p>}
  </>;
}
