import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowUpRight, Download } from 'lucide-react';
import { formatNumber } from './landingModel.js';
import {
  dateAt, extentOf, gapDrift, pathOf, segments, seriesNames, toCsv, yearRows,
} from './historyModel.js';

const CHART = { width: 960, height: 190, pad: 34 };

async function json(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw Error(`This basin has no published record (${response.status}).`);
  // A missing file is answered by the page shell with a 200, so the status alone
  // cannot tell data from the app's own HTML. Without this the reader is shown a
  // JSON parser's complaint instead of being told the data is not published.
  if (!(response.headers.get('content-type') || '').includes('json')) {
    throw Error('No monthly record is published for this basin yet.');
  }
  return response.json();
}

// The monthly record as a broken line: drawn where there are observations and
// absent where there are none, so a gap reads as a gap rather than as a value.
function Chart({ history, name, series }) {
  const [hover, setHover] = useState(null);
  const values = series.values;
  const extent = useMemo(() => extentOf(values), [values]);
  const width = CHART.width - CHART.pad * 2;
  const lines = useMemo(() => segments(values, extent, width, CHART.height), [values, extent, width]);
  if (!extent) return <p className="land-group-note">No observation in this window.</p>;

  const step = width / (values.length - 1);
  const years = history.years[1] - history.years[0] + 1;
  const ticks = [extent.high, (extent.high + extent.low) / 2, extent.low];
  return <figure className="land-hist-figure">
    <svg viewBox={`0 0 ${CHART.width} ${CHART.height + 40}`} role="img"
      aria-label={`${series.label} for every month from ${history.years[0]} to ${history.years[1]}`}
      onMouseLeave={() => setHover(null)}
      onMouseMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        const x = ((event.clientX - box.left) / box.width) * CHART.width - CHART.pad;
        const index = Math.round(x / step);
        setHover(index >= 0 && index < values.length ? index : null);
      }}>
      <g transform={`translate(${CHART.pad} 8)`}>
        {ticks.map((value, index) => {
          const y = (CHART.height / 2) * index;
          return <g key={index}>
            <line x1={0} x2={width} y1={y} y2={y} className="land-hist-grid"/>
            <text x={-6} y={y + 3} className="land-hist-axis" textAnchor="end">{formatNumber(value, 1)}</text>
          </g>;
        })}
        {lines.map((segment, index) => segment.length === 1
          ? <circle key={index} cx={segment[0].x} cy={segment[0].y} r={1.6} className="land-hist-dot"/>
          : <path key={index} d={pathOf(segment)} className="land-hist-line"/>)}
        {Array.from({ length: years }, (_, index) => index).filter(index => index % 2 === 0).map(index =>
          <text key={index} x={index * 12 * step} y={CHART.height + 16} className="land-hist-axis"
            textAnchor="middle">{history.years[0] + index}</text>)}
        {hover != null && values[hover] != null && <>
          <line x1={hover * step} x2={hover * step} y1={0} y2={CHART.height} className="land-hist-cursor"/>
          <circle cx={hover * step} cy={CHART.height - ((values[hover] - extent.low) / (extent.high - extent.low)) * CHART.height}
            r={3} className="land-hist-marker"/>
        </>}
      </g>
    </svg>
    <figcaption>
      {hover != null
        ? values[hover] == null
          ? `${dateAt(history, hover).label}: no observation`
          : `${dateAt(history, hover).label}: ${formatNumber(values[hover], 2)} ${series.unit}`
        : `${series.label} · ${series.unit} · ${history.years[0]}–${history.years[1]}`}
    </figcaption>
  </figure>;
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function BasinHistory({ basin }) {
  const [state, setState] = useState({ loading: true });
  const [retry, setRetry] = useState(0);
  const [name, setName] = useState(null);

  useEffect(() => {
    let live = true;
    setState({ loading: true });
    (async () => {
      const index = await json('/data/atlas/history/index.json');
      const history = await json(`${index.base_url}${basin.hybas_id}.json`);
      if (String(history.basin_id) !== String(basin.hybas_id)) {
        throw Error('The record does not belong to this basin. Refresh the page.');
      }
      if (live) setState({ index, history });
    })().catch(error => { if (live) setState({ error: error.message }); });
    return () => { live = false; };
  }, [basin.hybas_id, retry]);

  const names = state.history ? seriesNames(state.history) : [];
  const active = name && names.includes(name) ? name : names[0];
  const rows = useMemo(() => state.history && active ? yearRows(state.history, active) : [],
    [state.history, active]);
  const drift = useMemo(() => state.history && active ? gapDrift(state.history, active) : null,
    [state.history, active]);

  if (state.loading) return <p role="status" className="land-group-note">Loading this basin’s record…</p>;
  if (state.error) return <div className="land-sub-note" role="alert">
    <p>{state.error}</p>
    <p>Dated observations are published for level-12 basins in the two river systems.</p>
    <button onClick={() => setRetry(n => n + 1)}>Try again</button>
  </div>;

  const series = state.history.series[active];
  if (!series) return <p className="land-group-note">This basin carries no dated observation.</p>;
  const observed = series.observed_months;
  const total = state.history.months;
  return <>
    <div className="land-sub-note">
      <div className="land-sub-counts">
        <span className="land-sub-key">{state.history.years[0]}–{state.history.years[1]} monthly</span>
        <span>{observed} of {total} months observed</span>
        <span>{names.length} variables</span>
      </div>
      <p>These are the observations the climatologies were averaged from. A month with no
        observation is drawn as a gap and left empty in the download, never as a zero.</p>
      <p className="land-sub-links">
        <button type="button" className="land-hist-download"
          onClick={() => download(`basin-${basin.hybas_id}-monthly.csv`, toCsv(state.history), 'text/csv')}>
          <Download size={11}/> Download this basin, all variables (CSV)
        </button>
        <a href={`${state.index.base_url}${basin.hybas_id}.json`} download>JSON</a>
        <a href="/dynamic-atlas.html">Methods &amp; resolutions <ArrowUpRight size={11}/></a>
      </p>
    </div>

    <div className="land-sub-filters">
      <div className="land-sub-chips" role="group" aria-label="Choose a variable">
        {names.map(key => <button key={key} type="button" className={key === active ? 'active' : ''}
          onClick={() => setName(key)}>{state.history.series[key].label}</button>)}
      </div>
    </div>

    <Chart history={state.history} name={active} series={series}/>

    {drift?.growing && <p className="land-hist-warn">
      <AlertTriangle size={12}/>
      <span>This series loses months as the record goes on: {drift.early} missing in the first half
        against {drift.late} in the second. A trend computed straight through the gaps can be a
        trend in what the sensor delivered rather than in what happened here.</span>
    </p>}

    <table className="land-sub-table land-hist-table">
      <thead><tr>
        <th>Year</th><th>Observed</th><th>Mean</th><th>Lowest</th><th>Highest</th>
        <th>Annual total<br/><small>whole years only</small></th>
      </tr></thead>
      <tbody>{rows.map(row => <tr key={row.year} data-substitute-status={row.whole ? 'estimated' : 'empty'}>
        <th scope="row">{row.year}</th>
        <td className={row.whole ? '' : 'land-sub-nocompare'}>{row.observed} of 12</td>
        <td className="land-sub-num">{formatNumber(row.mean, 2)}</td>
        <td className="land-sub-num">{formatNumber(row.min, 2)}</td>
        <td className="land-sub-num">{formatNumber(row.max, 2)}</td>
        <td className="land-sub-num">{row.total == null
          ? <span className="land-sub-nocompare" title="Some months were not observed, so a total would be a sum of an incomplete year">—</span>
          : formatNumber(row.total, 1)}</td>
      </tr>)}</tbody>
    </table>

    <p className="land-sub-foot">
      {series.label} · {series.unit} · {series.asset} · {series.statistic?.replaceAll('_', ' ')} ·
      method <code>{series.method}</code>. {state.history.note}
    </p>
  </>;
}
