import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Info } from 'lucide-react';
import { formatNumber } from './landingModel.js';
import {
  basinIsPublished, categoriesOf, difference, inStoredUnits, isUpstream, payloadMatchesBasin,
  periodLabel, resolutionLabel, rowTotals, substituteRows, support,
} from './substitutesModel.js';

// The modal's own formatter, so a value reads the same in both tabs. It pins the
// locale on purpose: a decimal comma beside a thousands comma is unreadable, and a
// reader should not get a different number because of a browser setting.
const number = value => formatNumber(value, 2);

const signed = value => value == null ? null : `${value > 0 ? '+' : ''}${formatNumber(value, 2)}`;

async function json(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw Error(`Basin data could not be loaded (${response.status}).`);
  // A missing file is answered by the page shell with a 200, so the status alone
  // cannot tell data from the app's own HTML. Without this the reader is shown a
  // JSON parser's complaint instead of being told the data is not published.
  if (!(response.headers.get('content-type') || '').includes('json')) {
    throw Error('The basin data is not published at that address.');
  }
  return response.json();
}

// One expandable row of evidence. Collapsed it shows the two numbers; opened it
// shows why they differ, which is the part that stops the comparison being read as
// a reproduction test.
function Evidence({ row }) {
  const { meta, family } = row;
  const resolution = resolutionLabel(family);
  const period = periodLabel(meta);
  return <div className="land-sub-evidence">
    <div>
      <h4>Original · HydroATLAS</h4>
      <p>{meta.original?.dataset || 'Not recorded'}</p>
      <dl>
        <div><dt>Period</dt><dd>{meta.original?.period || 'Not recorded'}</dd></div>
        <div><dt>Citation</dt><dd>{meta.original?.citation || '—'}</dd></div>
        <div><dt>Units</dt><dd>{meta.unit || '—'}</dd></div>
      </dl>
      {meta.original?.catalogue && <a href={meta.original.catalogue} target="_blank" rel="noreferrer">
        Source catalogue <ArrowUpRight size={11}/></a>}
    </div>
    <div>
      <h4>Substitute · this project</h4>
      <p>{family?.source?.name || meta.substitute?.source_release || 'No estimate for this attribute'}</p>
      <dl>
        <div><dt>Period</dt><dd>{period ? `${period} (${meta.substitute?.statistic?.replaceAll('_', ' ') || 'derived'})` : 'Not computed'}</dd></div>
        <div><dt>Spatial</dt><dd>{resolution || 'Not recorded'}</dd></div>
        <div><dt>Support</dt><dd>{isUpstream(row.support) ? 'Everything draining through this basin' : 'This sub-basin only'}</dd></div>
        <div><dt>Units</dt><dd>{meta.substitute?.unit || '—'}</dd></div>
        <div><dt>Licence</dt><dd>{family?.source?.licence || '—'}</dd></div>
        <div><dt>Method</dt><dd><code>{meta.substitute?.method || '—'}</code></dd></div>
        <div><dt>Release</dt><dd><code>{meta.substitute?.source_release || '—'}</code></dd></div>
      </dl>
      {family?.source?.catalogue && <a href={family.source.catalogue} target="_blank" rel="noreferrer">
        Source catalogue <ArrowUpRight size={11}/></a>}
    </div>
    {family?.divergence?.length > 0 && <div className="land-sub-diverge">
      <h4>Why these are not the same measurement</h4>
      <ul>{family.divergence.map(note => <li key={note}>{note}</li>)}</ul>
    </div>}
    {family?.resolution?.support_change && <p className="land-sub-foot">
      {family.resolution.resampling}. {family.resolution.support_change}.</p>}
  </div>;
}

function Row({ row }) {
  const [open, setOpen] = useState(false);
  const change = difference(row);
  const converted = inStoredUnits(row);
  const backing = support(row);
  const period = periodLabel(row.meta);
  return <>
    <tr data-substitute-status={row.state} className={open ? 'is-open' : ''}>
      <td>
        <button type="button" className="land-sub-toggle" onClick={() => setOpen(value => !value)}
          aria-expanded={open} aria-label={`Evidence for ${row.label}`}>
          <strong>{row.label}</strong>
          <code>{row.column}</code>
        </button>
        <span className={`land-sub-cat cat-${row.category.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{row.category}</span>
      </td>
      <td className="land-sub-num">{number(row.original)}<small>{row.meta.unit}</small></td>
      <td className={`land-sub-num ${row.value != null ? 'land-sub-updated' : ''}`}>
        {number(row.value)}
        {row.value != null && <small>{row.meta.substitute?.unit}</small>}
      </td>
      <td className="land-sub-num">
        {change == null
          ? <span className="land-sub-nocompare" title={row.value == null ? 'No estimate for this attribute'
            : 'This estimate measures a different quantity from the published value, so subtracting one from the other would mean nothing'}>—</span>
          : <>
            <span className={change > 0 ? 'is-up' : change < 0 ? 'is-down' : ''}>{signed(change)}</span>
            {converted !== row.value && <small>{number(converted)} {row.meta.unit}</small>}
          </>}
      </td>
      <td>
        {period || <span className="land-sub-nocompare">—</span>}
        {backing && !backing.whole && <small>{backing.valid} of {backing.expected} periods</small>}
        {backing?.whole && <small>{backing.valid} periods</small>}
      </td>
      <td>{isUpstream(row.support) ? 'Upstream' : 'This basin'}</td>
    </tr>
    {open && <tr className="land-sub-detail"><td colSpan={6}><Evidence row={row}/></td></tr>}
  </>;
}

export default function BasinSubstitutes({ basin, filter, kind }) {
  const [state, setState] = useState({ loading: true });
  const [retry, setRetry] = useState(0);
  const [category, setCategory] = useState('all');
  const [onlyEstimated, setOnlyEstimated] = useState(false);

  useEffect(() => {
    let live = true;
    setState({ loading: true });
    (async () => {
      const index = await json('/data/atlas/basins/index.json');
      if (!basinIsPublished(index, basin)) {
        if (live) setState({ index, absent: true });
        return;
      }
      const [catalogue, values] = await Promise.all([
        json(index.catalogue), json(`${index.base_url}${basin.hybas_id}.json`),
      ]);
      if (!payloadMatchesBasin(catalogue, values, basin)) {
        throw Error('The basin file does not line up with the catalogue. Refresh the page.');
      }
      if (live) setState({ index, catalogue, values });
    })().catch(error => { if (live) setState({ error: error.message }); });
    return () => { live = false; };
  }, [basin.hybas_id, basin.basin_level, retry]);

  const rows = useMemo(() => {
    if (!state.catalogue) return [];
    const all = substituteRows(state.catalogue, state.values, filter, kind);
    return all.filter(row => (category === 'all' || row.category === category)
      && (!onlyEstimated || row.state === 'estimated'));
  }, [state.catalogue, state.values, filter, kind, category, onlyEstimated]);

  if (state.loading) return <p role="status" className="land-group-note">Loading this basin’s estimates…</p>;
  if (state.error) return <div className="land-sub-note" role="alert">
    <p>{state.error}</p>
    <button onClick={() => setRetry(n => n + 1)}>Try again</button>
  </div>;
  if (state.absent) return <div className="land-sub-note">
    <h3>Estimates are published for level-12 basins.</h3>
    <p>This is a level-{basin.basin_level} unit, which is a view of the level-12 basins inside it
      rather than a basin the extraction ran on. Zoom in to a level-12 basin to read its estimates.
      Values are never averaged up or copied across levels.</p>
    <a href="/roadmap.html#implementation-plan">How the levels relate <ArrowUpRight size={11}/></a>
  </div>;

  const totals = rowTotals(rows);
  const categories = categoriesOf(state.catalogue);
  return <>
    <div className="land-sub-note">
      <div className="land-sub-counts">
        <span className="land-sub-key">{totals.estimated} independently estimated</span>
        <span>{totals.originalOnly} published value only</span>
        <span>{totals.rows} shown of {state.catalogue.attributes.length}</span>
      </div>
      <p>An estimate is open data over a stated period, published beside the original and never in
        place of it. Different source, different method, different years: agreement between the two
        would not make either a reproduction of the other. Open a row for its sources, resolution
        and known divergences.</p>
      <p className="land-sub-links">
        <a href={`${state.index.base_url}${basin.hybas_id}.json`} download>Download this basin (JSON)</a>
        <a href="/data/atlas/catalogue.json" download>Attribute catalogue</a>
        <a href="/data/atlas/regional-coverage.json" download>Regional coverage</a>
        <a href="/dynamic-atlas.html">Methods &amp; resolutions <ArrowUpRight size={11}/></a>
      </p>
    </div>

    <div className="land-sub-filters">
      <div className="land-sub-chips" role="group" aria-label="Filter by category">
        <button type="button" className={category === 'all' ? 'active' : ''}
          onClick={() => setCategory('all')}>All themes</button>
        {categories.map(name => <button key={name} type="button"
          className={`cat-${name.toLowerCase().replace(/[^a-z]+/g, '-')} ${category === name ? 'active' : ''}`}
          onClick={() => setCategory(name)}>{name}</button>)}
      </div>
      <label className="land-sub-only">
        <input type="checkbox" checked={onlyEstimated} onChange={e => setOnlyEstimated(e.target.checked)}/>
        Only attributes with an estimate
      </label>
    </div>

    <table className="land-sub-table">
      <thead><tr>
        <th>Attribute</th>
        <th>Published<br/><small>HydroATLAS</small></th>
        <th>Estimate<br/><small>this project</small></th>
        <th>Difference<br/><small>same units only</small></th>
        <th>Period<br/><small>and record behind it</small></th>
        <th>Measured over</th>
      </tr></thead>
      <tbody>{rows.map(row => <Row key={row.column} row={row}/>)}</tbody>
    </table>
    {!rows.length && <p className="land-group-note">Nothing matches that filter.</p>}
    <p className="land-sub-foot"><Info size={11}/> {state.catalogue.reading?.resolution}</p>
  </>;
}
