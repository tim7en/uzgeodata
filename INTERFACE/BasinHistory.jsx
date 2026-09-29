import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowUpRight, Download } from 'lucide-react';
import { formatNumber } from './landingModel.js';
import {
  dateAt, extentOf, extractedLength, gapDrift, pathOf, segments, seriesNames, toCsv, yearRows,
} from './historyModel.js';
import { useWidth } from './ReportChart.jsx';
import { CONTINUATION_VARIABLES, continuationFor } from './continuationModel.js';

const CHART = { height: 190, pad: 38 };

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
// Drawn at the width it is given rather than scaled from a fixed viewBox: a
// 960-unit drawing shrunk onto a phone set its axis labels at four pixels.
function Chart({ history, name, series, estimate }) {
  const [frame, frameWidth] = useWidth();
  return <div ref={frame} className="land-hist-frame">{frameWidth > 0
    && <Plot history={history} name={name} series={series} estimate={estimate} outer={frameWidth}/>}</div>;
}

/**
 * The estimate that continues a series past its source, on the record's own
 * month positions, and only where the record has no observation: an estimate
 * never stands in for a month that was observed.
 */
function estimateFor(history, key, document) {
  const values = history.series[key].values;
  const rows = CONTINUATION_VARIABLES[key] ? continuationFor(document, key, 'local')?.estimated?.rows : null;
  if (!rows?.length) return null;
  const out = values.map(() => null);
  for (const row of rows) {
    const position = (row.year - history.years[0]) * 12 + row.month - 1;
    if (position >= 0 && position < out.length && values[position] == null) out[position] = row;
  }
  return out.some(Boolean) ? out : null;
}

function Plot({ history, name, series, estimate, outer }) {
  const [hover, setHover] = useState(null);
  const values = series.values;
  const estimated = useMemo(() => (estimate ? estimate.map(row => row?.value ?? null) : null), [estimate]);
  const extent = useMemo(() => extentOf(estimated ? values.map((value, i) => value ?? estimated[i]) : values),
    [values, estimated]);
  const width = outer - CHART.pad - 12;
  const lines = useMemo(() => segments(values, extent, width, CHART.height), [values, extent, width]);
  const estimateLines = useMemo(() => (estimated ? segments(estimated, extent, width, CHART.height) : []),
    [estimated, extent, width]);
  if (!extent) return <p className="land-group-note">No source value in this window.</p>;

  const step = width / (values.length - 1);
  const years = history.years[1] - history.years[0] + 1;
  const ticks = [extent.high, (extent.high + extent.low) / 2, extent.low];
  // A tap reads a month the same way a hover does.
  const pick = event => {
    const box = event.currentTarget.getBoundingClientRect();
    const index = Math.round((event.clientX - box.left - CHART.pad) / step);
    setHover(index >= 0 && index < values.length ? index : null);
  };
  const yearStep = Math.max(1, Math.ceil(years / Math.max(1, Math.floor(width / 48))));
  return <figure className="land-hist-figure">
    <svg width={outer} height={CHART.height + 40} role="img"
      aria-label={`${series.label} for every month from ${history.years[0]} to ${history.years[1]}`}
      onPointerLeave={event => { if (event.pointerType === 'mouse') setHover(null); }}
      onPointerDown={pick} onPointerMove={pick}>
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
        {estimateLines.map((segment, index) => <path key={`e${index}`} d={pathOf(segment)} className="land-hist-estimate"/>)}
        {Array.from({ length: years }, (_, index) => index).filter(index => index % yearStep === 0).map(index =>
          <text key={index} x={index * 12 * step} y={CHART.height + 16} className="land-hist-axis"
            textAnchor="middle">{history.years[0] + index}</text>)}
        {hover != null && (values[hover] ?? estimated?.[hover]) != null && <>
          <line x1={hover * step} x2={hover * step} y1={0} y2={CHART.height} className="land-hist-cursor"/>
          <circle cx={hover * step} cy={CHART.height - (((values[hover] ?? estimated[hover]) - extent.low) / (extent.high - extent.low)) * CHART.height}
            r={3} className={values[hover] == null ? 'land-hist-marker estimated' : 'land-hist-marker'}/>
        </>}
      </g>
    </svg>
    <figcaption>
      {hover != null
        ? values[hover] != null
          ? `${dateAt(history, hover).label}: ${formatNumber(values[hover], 2)} ${series.unit}`
          : estimate?.[hover]
            ? `${dateAt(history, hover).label}: ${formatNumber(estimate[hover].value, 2)} ${series.unit} · estimated`
              + `${estimate[hover].errorP90 ? ` ±${formatNumber(estimate[hover].errorP90, 2)}` : ''}`
            : `${dateAt(history, hover).label}: no source value`
        : `${series.label} · ${series.unit} · ${history.years[0]}–${history.years[1]}`
          + `${estimate ? ' · dashed: estimated past the end of the source' : ''}`}
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
      // The continuation is optional: without it the record simply ends where
      // its source does, as it did before.
      const continuation = await fetch(`/data/atlas/climate-continuation/basins/${basin.hybas_id}.json`)
        .then(response => (response.ok && (response.headers.get('content-type') || '').includes('json') ? response.json() : null))
        .catch(() => null);
      if (live) setState({ index, history, continuation });
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
    <p>Dated source values are published for level-12 basins in the two river systems.</p>
    <button onClick={() => setRetry(n => n + 1)}>Try again</button>
  </div>;

  const series = state.history.series[active];
  if (!series) return <p className="land-group-note">This basin carries no dated source value.</p>;
  const observed = series.observed_months;
  const total = extractedLength(state.history, series);
  return <>
    <div className="land-history-actions">
        <button type="button" className="land-hist-download"
          onClick={() => download(`basin-${basin.hybas_id}-monthly.csv`, toCsv(state.history), 'text/csv')}>
          <Download size={11}/> Download this basin, all variables (CSV)
        </button>
    </div>

    <div className="land-sub-filters">
      <div className="land-sub-chips" role="group" aria-label="Choose a variable">
        {names.map(key => <button key={key} type="button" className={key === active ? 'active' : ''}
          onClick={() => setName(key)}>{state.history.series[key].label}</button>)}
      </div>
    </div>

    {(active === 'snw_pc_s' || series.trend_use === 'withdrawn') && <p className="land-hist-warn" role="note">
      <AlertTriangle size={12}/><span>Snow is not for trend analysis. Regional missing months increase
      across this record; the cause is unresolved. Values remain available for inspection.</span>
    </p>}
    <Chart history={state.history} name={active} series={series}
      estimate={state.continuation ? estimateFor(state.history, active, state.continuation) : null}/>

    <div className="land-sub-note">
      <div className="land-sub-counts">
        <span className="land-sub-key">{state.history.years[0]}–{state.history.years[1]} monthly</span>
        <span>{observed} of {total} months with source values</span>
        <span>{names.length} variables</span>
      </div>
      <p>Monthly gridded estimates and reanalysis for this basin, not field measurements. Their period may differ from the climatologies. A month with no
        source value is drawn as a gap and left empty in the download, never as a zero.</p>
      <p className="land-sub-links">

        <a href={`${state.index.base_url}${basin.hybas_id}.json`} download>JSON</a>
        <button type="button" className="land-hist-download" onClick={() => download(
          `basin-${basin.hybas_id}-monthly-metadata.json`, JSON.stringify({ ...state.history,
            series: Object.fromEntries(Object.entries(state.history.series).map(([key, { values, ...meta }]) => [key, meta]))
          }, null, 2), 'application/json')}>Download metadata &amp; limitations</button>
        <a href="/dynamic-atlas.html">Methods &amp; resolutions <ArrowUpRight size={11}/></a>
      </p>
    </div>

    {drift?.growing && <p className="land-hist-warn">
      <AlertTriangle size={12}/>
      <span>This series loses months as the record goes on: {drift.early} missing in the first half
        against {drift.late} in the second. A trend computed straight through the gaps can be a
        trend in what the sensor delivered rather than in what happened here.</span>
    </p>}

    <table className="land-sub-table land-hist-table">
      <thead><tr>
        <th>Year</th><th>Observed</th><th>Mean</th><th>Lowest</th><th>Highest</th>
        <th>Annual total<br/><small>monthly fluxes, whole years only (mm)</small></th>
      </tr></thead>
      <tbody>{rows.map(row => <tr key={row.year} data-substitute-status={row.whole ? 'estimated' : 'empty'}>
        <th scope="row">{row.year}</th>
        <td className={row.whole ? '' : 'land-sub-nocompare'}>{row.observed} of {row.months.length}</td>
        <td className="land-sub-num">{formatNumber(row.mean, 2)}</td>
        <td className="land-sub-num">{formatNumber(row.min, 2)}</td>
        <td className="land-sub-num">{formatNumber(row.max, 2)}</td>
        <td className="land-sub-num">{row.total == null
          ? <span className="land-sub-nocompare" title="Totals require 12 observed months and a quantity in millimetres per month">—</span>
          : formatNumber(row.total, 1)}</td>
      </tr>)}</tbody>
    </table>

    <p className="land-sub-foot">
      {series.label} · {series.unit} · {series.asset} · {series.statistic?.replaceAll('_', ' ')} ·
      method <code>{series.method}</code>. {state.history.note}
    </p>
  </>;
}
