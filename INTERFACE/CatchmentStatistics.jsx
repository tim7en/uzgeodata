import React, { useEffect, useMemo, useState } from 'react';
import { aggregateCatchment, catchmentMembers, decodeMatrix, MORPHOLOGY_FIELDS, statisticsCsv } from './catchmentStatisticsModel.js';
import { toCsv } from './aoiModel.js';
import { formatNumber } from './landingModel.js';

const INDEX = '/data/atlas/catchments/index.json';
const matrices = new Map();
async function json(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok || !response.headers.get('content-type')?.includes('json')) throw Error('Catchment statistics are not available.');
  return response.json();
}
async function matrix(index, name, signal) {
  const entry = index.series[name];
  if (matrices.has(entry.url)) return matrices.get(entry.url);
  if (typeof DecompressionStream === 'undefined') throw Error('This browser cannot read compressed statistics. Use a current browser.');
  const response = await fetch(entry.url, { signal });
  if (!response.ok) throw Error('Monthly catchment data could not load.');
  const compressed = await response.arrayBuffer();
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', compressed))].map(b => b.toString(16).padStart(2, '0')).join('');
  if (hash !== entry.sha256) throw Error('Monthly catchment data failed its integrity check. Retry after refreshing.');
  const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
  const values = decodeMatrix(new Uint8Array(await new Response(stream).arrayBuffer()), index);
  if (matrices.size >= 2) matrices.delete(matrices.keys().next().value);
  matrices.set(entry.url, values);
  return values;
}
function save(name, value, type) {
  const url = URL.createObjectURL(new Blob([value], { type }));
  const link = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// A trace or an aggregation can reject the basin it was handed: an identifier the
// package does not carry, or a matrix that does not match its index. Those are
// answers about the data, not React failures, so they come back as a value and are
// shown like any other message. Throwing out of a useMemo would take the modal down.
function attempt(work) {
  try {
    return { value: work() };
  } catch (cause) {
    return { error: cause.message };
  }
}

export default function CatchmentStatistics({ basin }) {
  // Only level 12 carries a published catchment, and one monthly matrix is several
  // megabytes. Settling that before the first fetch keeps a level-7 selection from
  // downloading a package it could never aggregate.
  const supported = Number(basin.basin_level) === 12;
  const [data, setData] = useState(null), [values, setValues] = useState(null);
  const [name, setName] = useState('pre_mm_s');
  const [error, setError] = useState(''), [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!supported) return undefined;
    const controller = new AbortController();
    setError(''); setData(null);
    json(INDEX, controller.signal).then(async index => {
      const morphology = await json(index.morphology_url, controller.signal);
      if (!controller.signal.aborted) setData({ index, morphology });
    }).catch(cause => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [retry, supported]);
  useEffect(() => {
    if (!data || !supported) return undefined;
    const controller = new AbortController();
    setValues(null); setError('');
    matrix(data.index, name, controller.signal).then(result => {
      if (!controller.signal.aborted) setValues({ name, result });
    }).catch(cause => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [data, name, supported]);
  const members = useMemo(() => data && supported
    ? attempt(() => catchmentMembers(data.index, basin.hybas_id)) : null, [data, basin.hybas_id, supported]);
  const result = useMemo(() => data && members?.value?.length && values?.name === name
    ? attempt(() => aggregateCatchment(data.index, values.result, members.value, name)) : null, [data, values, members, name]);
  if (!supported) return <p className="land-group-note">Catchment statistics are published for level-12 basins. Search for a level-12 identifier in the basin finder.</p>;
  const ids = members?.value ?? [];
  const rows = result?.value;
  const failure = error || members?.error || result?.error;
  const morphology = data?.morphology.basins[String(basin.hybas_id)];
  const meta = data?.index.series[name]?.meta;
  const provenance = data && [...new Set(ids.map(i => data.index.series[name].provenance_ids[i]))].map(i => data.index.series[name].provenance[i]);
  const metadata = data && {
    outlet_hybas_id: basin.hybas_id, scope: 'Selected polygon plus all connected upstream level-12 polygons, including virtual links',
    basin_ids: ids.map(i => data.index.ids[i]), series: name, source_metadata: provenance,
    aggregation: 'Local SUB_AREA-weighted mean. Min/max are extrema among sub-basin monthly values, not pixel-level spatial extremes.',
    missingness: 'Missing basins are excluded from covered-area statistics. Full-catchment means and totals are null unless every member has an observation. No extrapolation.',
    total: rows?.total, max_input_rounding_error: data.index.max_quantization_error,
    morphology, morphology_methods: data.morphology.notes,
    source_history_sha256: data.index.history_sha256, source_geometry_sha256: data.morphology.source_geometry_sha256,
  };
  return <div className="land-catchment-stats">
    <h3>Whole upstream catchment</h3>
    <p>Selected polygon and every connected upstream sub-basin. These summaries use published satellite and model-based records.</p>
    {failure && <p className="land-stats-error" role="alert">{failure} <button onClick={() => setRetry(n => n + 1)}>Retry statistics</button></p>}
    {!data && !failure && <p role="status">Loading catchment statistics…</p>}
    {data && <>
      <p><strong>{formatNumber(ids.length)} sub-basins</strong> · {formatNumber(morphology?.traced_area_km2)} km² traced · {formatNumber(basin.upstream_km2)} km² reported upstream.</p>
      <div className="land-stats-actions">
        <button disabled={!rows} onClick={() => save(`catchment-${basin.hybas_id}-${name}.csv`, statisticsCsv(basin.hybas_id, name, meta, rows), 'text/csv')}>Download monthly statistics (CSV)</button>
        <button disabled={!rows} onClick={() => save(`catchment-${basin.hybas_id}-${name}.json`, JSON.stringify({ ...metadata, monthly: rows.rows }, null, 2), 'application/json')}>Download statistics &amp; metadata (JSON)</button>
      </div>
      <label className="land-stats-variable">Monthly variable
        <select value={name} onChange={event => { setValues(null); setName(event.target.value); }}>
          {Object.entries(data.index.series).map(([key, entry]) => <option key={key} value={key}>{entry.meta.label}</option>)}
        </select>
      </label>
      {!rows && !failure && <p role="status">Reading the monthly data package…</p>}
      {name === 'snw_pc_s' && <p className="land-hist-warn">Snow is not suitable for trend analysis. Missing observations vary across the record.</p>}
      <p>Mean is weighted by the area with observations. Min/max compare sub-basin values, not individual pixels. Coverage is shown for each month; a full-catchment total is withheld when any basin is missing.</p>
      {rows && <>
        <p>{rows.total.note}</p>
        <div className="land-stats-table"><table>
          <caption>Monthly catchment statistics · {meta.unit}</caption>
          <thead><tr><th>Month</th><th>Mean (covered area)</th><th>Min sub-basin</th><th>Max sub-basin</th><th>{rows.total.label}{rows.total.unit && ` (${rows.total.unit})`}</th><th>Area coverage</th></tr></thead>
          <tbody>{rows.rows.map(row => <tr key={`${row.year}-${row.month}`}>
            <th scope="row">{row.year}-{String(row.month).padStart(2, '0')}</th>
            <td>{formatNumber(row.mean_observed_area, 2)}</td><td>{formatNumber(row.min_subbasin_value, 2)}</td><td>{formatNumber(row.max_subbasin_value, 2)}</td>
            <td>{formatNumber(row.total_full_catchment, 2)}</td><td>{formatNumber(row.area_coverage_percent, 1)}% <small>{row.observed_basins}/{row.basin_count} basins</small></td>
          </tr>)}</tbody>
        </table></div>
      </>}
      <h3>Catchment morphology</h3>
      <div className="land-stats-actions">
        <button disabled={!morphology} onClick={() => save(`catchment-${basin.hybas_id}-morphology.csv`,
          toCsv(['outlet_hybas_id', 'metric', 'label', 'value', 'unit'], MORPHOLOGY_FIELDS.map(([key, label, unit]) => [basin.hybas_id, key, label, morphology[key], unit])), 'text/csv')}>Download morphology (CSV)</button>
      </div>
      {morphology ? <dl className="land-morphology">{MORPHOLOGY_FIELDS.map(([key, label, unit]) => <div key={key}>
        <dt>{label}</dt><dd>{formatNumber(morphology[key], 2)} {unit}</dd>
      </div>)}</dl> : <p>Morphology has not been published for this catchment.</p>}
      <details><summary>Methods, sources &amp; limitations</summary>
        {data.morphology.notes.map(note => <p key={note}>{note}</p>)}
        <p>Monthly inputs are rounded to 0.0001 native units for the compact package. Download JSON to retain coverage and source metadata.</p>
        <p><a href="https://data.hydrosheds.org/file/technical-documentation/HydroATLAS_TechDoc_v10_1.pdf">HydroATLAS documentation</a> · <a href="https://data.hydrosheds.org/file/technical-documentation/HydroBASINS_TechDoc_v1c.pdf">HydroBASINS documentation</a></p>
      </details>
    </>}
  </div>;
}
