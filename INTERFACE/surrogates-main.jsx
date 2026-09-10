import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './roadmap.css';

const number = (value, digits = 0) => value == null ? '—'
  : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
const percent = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`;

const USAGE = [
  {
    title: 'Filling attributes the atlas leaves empty or stale',
    body: 'The atlas records zero glacier cover in every Pskem unit, while the current GLIMS release maps '
      + 'roughly 3.5 percent of the pilot as glacierised. The 2012 snapshot appears to lack Western Tien Shan '
      + 'coverage rather than to disagree about area. For a glacier-fed headwater study, the surrogate is the '
      + 'estimate to investigate alongside the archived atlas value; the coverage explanation still needs source review.',
  },
  {
    title: 'Refreshing epochs that have aged out',
    body: 'Land cover in the atlas describes the year 2000, population 2010, irrigation 2005 and night lights 2008. '
      + 'The surrogates carry 2015 land cover and built surface, 2015 population and a 1991-2020 climate normal. '
      + 'Where a question is about the present rather than about the atlas, the surrogate epoch is the relevant one.',
  },
  {
    title: 'Cross-checking our own pipeline',
    body: 'Where the surrogate shares the atlas source lineage it acts as a control on our geometry, support rule '
      + 'and grid alignment rather than on the data. Slope reproduces to 0.1 percent of the stored magnitude and '
      + 'population to under 9 percent, which is evidence that the basin support and 15 arc-second grid are wired '
      + 'up correctly before any harder attribute is trusted.',
  },
  {
    title: 'Screening which attributes are safe to use here',
    body: 'The fidelity class is an explicit warning label. Soil water content, night lights and human footprint '
      + 'are published in their own units because no defensible conversion to the stored scale exists, and soil '
      + 'organic carbon diverges by roughly eight times. Those four should not enter an index or a regression '
      + 'against atlas values without a decision recorded first.',
  },
  {
    title: 'Sharpening boundary-sensitive shares',
    body: 'Glacier and protected-area polygons are painted at 30 m and aggregated to the pilot grid. Lake shares use '
      + 'exact geodesic polygon intersection, and land cover, built surface and surface water are aggregated from 100 m and '
      + '30 m sources. For small headwater units, where a 15 arc-second cell is a large fraction of the basin, '
      + 'that is a real resolution gain over a cell-centre method.',
  },
];

const LIMITS = [
  'No attribute has passed the independent scientific reproduction gate. That needs an independent operator and a method review; neither has happened.',
  'A surrogate is never a reproduction. Differences against the original are diagnostics, so agreement cannot certify and disagreement cannot invalidate.',
  'Two sources are moving targets. GLIMS and WDPA are read from collections named "current", so a rebuild from scratch at a later date will return different glacier and protected-area shares.',
  'Earth Engine assets carry no content hash to pin, and some are already deprecated upstream. The run pins the derived raster instead.',
  'The atlas attributes are static or climatological single values, so nothing about them can be verified through time. Only a surrogate against independent observations can be.',
  'Reproduction needs an Earth Engine account and a local copy of the 5.95 GB original geodatabase, which the pipeline does not fetch.',
];

function Families({ families, filter, query }) {
  const rows = families.filter(f => (filter === 'all'
      || (filter === 'estimated' ? f.estimated_attributes > 0
        : filter === 'compared' ? f.compared_attributes > 0 : f.estimated_attributes < f.attributes))
    && `${f.family} ${f.original.dataset} ${f.surrogate.name}`.toLowerCase().includes(query.toLowerCase()));
  return <>
    <p>{rows.length} of {families.length} families · {rows.reduce((n, f) => n + f.attributes, 0)} attributes.</p>
    <div className="attributes">{rows.map(f => <details key={f.family}>
      <summary><code>{f.family}</code><span>{f.original.dataset}</span>
        <small>{f.estimated_attributes ? `${f.fidelity.replaceAll('_', ' ')}${f.estimated_attributes < f.attributes ? ` · ${f.estimated_attributes} of ${f.attributes}` : ''}` : 'no surrogate'}</small></summary>
      <div className="recipe">
        <p><strong>Original:</strong> {f.original.dataset} · {f.original.citation} · {f.original.units} · {f.attributes} attribute{f.attributes === 1 ? '' : 's'}</p>
        {f.estimated_attributes ? <>
          <p><strong>Surrogate:</strong> <a href={f.surrogate.catalogue_url} target="_blank" rel="noreferrer">{f.surrogate.name}</a> · {f.surrogate.provider} · {f.surrogate.period} · {f.surrogate.licence}</p>
          <p>Native {f.resolution.native_scale_m ? `${number(f.resolution.native_scale_m, 1)} m` : f.resolution.grid}
            {f.resolution.native_arcsec ? ` (${f.resolution.native_arcsec} arc-seconds)` : ''} · processing grid {f.resolution.processing_grid_arcsec} arc-seconds · {f.resolution.resampling}</p>
          <p>Units {f.units.surrogate} against stored {f.units.reference_stored} — {f.units.convertible
            ? `convertible, factor ${f.units.factor}` : 'not convertible, so no difference is computed'}.</p>
          {f.relative_mae_mean != null
            ? <p>Mean relative difference across {f.compared_attributes} comparable attribute{f.compared_attributes === 1 ? '' : 's'}: <strong>{percent(f.relative_mae_mean)}</strong> of the mean stored magnitude, spanning {percent(f.relative_mae_min)} to {percent(f.relative_mae_max)}. A diagnostic, not a test.</p>
            : <p>No relative difference is reported: the units are not convertible, or the stored reference is zero throughout the pilot.</p>}
        </> : <p><strong>No surrogate in this pass.</strong> {f.pending_reason}</p>}
        {f.estimated_attributes > 0 && f.estimated_attributes < f.attributes
          && <p><strong>Partly covered:</strong> {f.attributes - f.estimated_attributes} of {f.attributes} attributes have no open surrogate. {f.pending_reason}</p>}
        <ul>{f.divergence_notes.map(note => <li key={note}>{note}</li>)}</ul>
      </div>
    </details>)}</div>
  </>;
}

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  useEffect(() => {
    fetch('/data/atlas/surrogate-science.json', { cache: 'no-store' })
      .then(r => { if (!r.ok) throw new Error(`Surrogate record request failed (${r.status})`); return r.json(); })
      .then(next => {
        if (!Array.isArray(next.families) || !next.pilot) throw new Error('Invalid surrogate record');
        setData(next);
      })
      .catch(e => setError(e.message));
  }, []);

  return <main>
    <p><a href="/dynamic-atlas.html">Dynamic HydroATLAS: fetched results, resolutions and update audit →</a></p>
    <nav><a href="/roadmap.html">← Atlas roadmap</a><a href="/data/atlas/surrogates.md" download>Surrogate plan ↓</a></nav>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Loading the surrogate record…</p>}
    {data && <>
      <header className="hero">
        <p className="eyebrow">Open-data surrogates · {data.run_id}</p>
        <h1>What we built beside the atlas.</h1>
        <p>{data.release_rule} {data.comparison_policy}</p>
      </header>

      <section aria-label="Coverage">
        <div className="metrics">
          <div><strong>{number(data.pilot.attributes)}</strong><span>attributes in the pilot</span></div>
          <div><strong>{number(data.pilot.candidates)}</strong><span>rebuilt from original-vintage sources</span></div>
          <div><strong>{number(data.pilot.surrogates)}</strong><span>carry an open-data surrogate</span></div>
          <div><strong>{number(data.pilot.without_estimate)}</strong><span>have no estimate yet</span></div>
          <div><strong>{number(data.pilot.independently_reproduced)}</strong><span>independently reproduced</span></div>
        </div>
        <p>Of the {number(data.pilot.candidates)} original-vintage candidates, {number(data.pilot.candidate_pass)} pass
          their declared tolerance in all {data.pilot.basins} basins. The remaining four are elevation attributes whose
          differences are published rather than absorbed into a wider tolerance.</p>
      </section>

      <section aria-label="Method">
        <h2>Method</h2>
        <p>Each family declares an open dataset, a fidelity class, a native resolution, the shared 15 arc-second
          processing grid, a resampling rule and a unit conversion. Builders return values in the surrogate's own
          physical units; the runner applies the conversion factor only where the registry says the units are
          convertible. Class fractions are computed at the source's native resolution before aggregation, never by
          classifying an already-resampled grid. Polygon sources are handled either by painting at 30 m and then
          aggregating, or by exact geodesic intersection where the boundary matters more than the grid.</p>
        <div className="batch-table-scroll"><table>
          <thead><tr><th>Fidelity</th><th>Attributes</th><th>Meaning</th></tr></thead>
          <tbody>{Object.entries(data.pilot.by_fidelity).map(([name, count]) => <tr key={name}>
            <td>{name.replaceAll('_', ' ')}</td><td>{count}</td><td>{data.fidelity_classes[name]}</td></tr>)}</tbody>
        </table></div>
        <p>{Object.entries(data.excluded_sources).map(([asset, why]) => <React.Fragment key={asset}>
          <strong>Excluded: <code>{asset}</code></strong> — {why}</React.Fragment>)}</p>
      </section>

      <section aria-label="Verification">
        <h2>Verification</h2>
        <h3>Spatially, against the atlas</h3>
        <p>{data.verification.spatial.basis} {number(data.verification.spatial.convertible_attributes)} surrogates are
          unit-convertible and {number(data.verification.spatial.with_reference_magnitude)} of those sit against a
          non-zero stored value, which is the set where a relative difference means anything.</p>
        <div className="two-columns">
          <div><h3>Closest to the atlas</h3><ol className="ranked">{data.verification.spatial.closest.map(a =>
            <li key={a.attribute}><code>{a.attribute}</code> <span>{percent(a.relative_mae)}</span></li>)}</ol></div>
          <div><h3>Furthest from the atlas</h3><ol className="ranked">{data.verification.spatial.furthest.map(a =>
            <li key={a.attribute}><code>{a.attribute}</code> <span>{percent(a.relative_mae)}</span></li>)}</ol></div>
        </div>
        <h3>Temporally, against observations</h3>
        <p>{data.verification.temporal.note} The available basis is {number(data.verification.temporal.stations)} hydromet
          stations carrying {number(data.verification.temporal.monthly_records)} monthly records from{' '}
          {data.verification.temporal.first_year} to {data.verification.temporal.last_year}
          ({data.verification.temporal.variables.map(v => v.replaceAll('_', ' ')).join(', ')}). That supports a genuine
          through-time test for the {data.verification.temporal.testable_families.join(' and ')} families and for
          nothing else in the registry today.</p>
      </section>

      <section aria-label="Scope and scale">
        <h2>Scope, and what full coverage would cost</h2>
        <p>The pilot is {data.pilot.basins} level-12 units. The full Amu Darya and Syr Darya systems hold{' '}
          <strong>{number(data.domain.basins)}</strong> level-12 units covering {number(data.domain.total_area_km2)} km²,
          median unit {data.domain.median_unit_km2} km². That is {number(data.scale_projection.basin_scale_factor)}×
          the basins and {number(data.scale_projection.cell_scale_factor)}× the cells.</p>
        <div className="batch-table-scroll"><table>
          <thead><tr><th>Processing grid</th><th>Columns × rows</th><th>Megacells</th><th>GB per float32 band</th></tr></thead>
          <tbody>{Object.values(data.domain.grids).map(g => <tr key={g.arcsec}>
            <td>{g.arcsec} arc-second{g.arcsec === 1 ? '' : 's'}</td><td>{number(g.columns)} × {number(g.rows)}</td>
            <td>{number(g.megacells, 1)}</td><td>{g.gigabytes_per_float32_band}</td></tr>)}</tbody>
        </table></div>
        <p><strong>Measured at full extent on this machine:</strong> loading the {number(data.domain.basins)}-unit frame
          takes {data.scale_projection.measured.frame_load_seconds} s, rasterising it to the 15 arc-second grid{' '}
          {data.scale_projection.measured.rasterise_seconds} s, and one label-indexed zonal pass{' '}
          {data.scale_projection.measured.bincount_pass_seconds} s. Across{' '}
          {data.scale_projection.measured.reduction_passes} passes that is{' '}
          <strong>{data.scale_projection.reduction_minutes_bincount} minutes</strong> of reduction.</p>
        <p><strong>The kernel has to change first.</strong> The pilot reduces by masking the grid once per basin, which
          costs {data.scale_projection.measured.per_basin_mask_seconds} s per basin and would take{' '}
          {data.scale_projection.reduction_hours_current_kernel} hours over the full domain — about{' '}
          {number(data.scale_projection.kernel_speedup_required)}× slower than the label-indexed path. This is a known,
          bounded change, not a research problem.</p>
        <p><strong>Acquisition is the uncertain half.</strong> {data.scale_projection.basis} Scaled linearly from the
          pilot cold run, source acquisition is about {data.scale_projection.acquisition_hours_linear} hours, of which{' '}
          {data.scale_projection.acquisition_hours_linear_modis_only} hours is the MODIS daily snow reduction alone,
          producing roughly {data.scale_projection.raster_gigabytes_15arcsec} GB of raster at 15 arc-seconds.
          Synchronous downloads cannot carry that: a single band at full extent already exceeds the request limit, so
          batch export replaces it and the real figure depends on queueing rather than on arithmetic.</p>
      </section>

      <section aria-label="Usage">
        <h2>Where these numbers are usable</h2>
        {USAGE.map(item => <div key={item.title} className="usage">
          <h3>{item.title}</h3><p>{item.body}</p></div>)}
      </section>

      <section className="contract" aria-label="Limits">
        <h2>What this is not.</h2>
        <ul>{LIMITS.map(limit => <li key={limit}>{limit}</li>)}</ul>
        <div className="downloads">
          <a href="/data/atlas/surrogates.md" download>Surrogate methodology ↓</a>
          <a href="/data/atlas/surrogate-science.json" download>This record as JSON ↓</a>
          <a href={`/data/atlas/runs/${data.run_id}/surrogate-registry.csv`} download>Per-attribute registry ↓</a>
          <a href={`/data/atlas/runs/${data.run_id}/observations.csv`} download>All basin observations ↓</a>
        </div>
      </section>

      <section aria-label="Family registry">
        <div className="section-heading"><h2>Family registry</h2><span>{data.families.length} families</span></div>
        <div className="filters">
          <label>Search<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Dataset, family or source"/></label>
          <label>Show<select aria-label="Show" value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">All families</option>
            <option value="estimated">With a surrogate</option>
            <option value="compared">With a measured difference</option>
            <option value="pending">Without a surrogate</option>
          </select></label>
        </div>
        <Families families={data.families} filter={filter} query={query}/>
      </section>

      <footer>Generated {data.generated_at} from run {data.run_id}. Every figure on this page is measured or read
        from that run; projections to the full domain are labelled as extrapolations.</footer>
    </>}
  </main>;
}

createRoot(document.getElementById('root')).render(<App/>);
