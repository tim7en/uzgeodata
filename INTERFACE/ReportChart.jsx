import React, { useEffect, useMemo, useRef, useState } from 'react';
import { formatNumber } from './landingModel.js';
import { monthlySeries } from './continuationModel.js';
import { chartWindow, monthlyNormals } from './poiModel.js';
import './reportChart.css';

const PAD = { top: 10, right: 10, bottom: 22, left: 44 };
const HEIGHT = 220;
const SPANS = [[36, 'Last 3 years'], [120, '10 years'], [null, 'Full record']];
const label = row => `${row.year}-${String(row.month).padStart(2, '0')}`;

// Runs of consecutive months, so a missing month is drawn as a gap and an
// estimate is never joined to the observation it follows.
function runs(rows, pick) {
  const out = [];
  let current = [];
  rows.forEach((row, index) => {
    const value = pick(row);
    const joined = current.length && rows[index - 1].key === row.key - 1;
    if (value === null || value === undefined) { if (current.length) out.push(current); current = []; return; }
    if (current.length && !joined) { out.push(current); current = []; }
    current.push({ row, value });
  });
  if (current.length) out.push(current);
  return out;
}

export function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/**
 * The report's monthly series against its own normal.
 *
 * A reader on a phone came for "is it unusual now", so the chart opens on the
 * last three years rather than on 288 months squeezed into 350 pixels. The
 * estimate beyond the observed record keeps its own mark and its own error band,
 * so a month inside that band reads as indistinguishable from normal.
 */
export default function ReportChart({ report }) {
  const hasUpstream = !report.continuation?.upstreamWithheld;
  const [scope, setScope] = useState('local');
  const [span, setSpan] = useState(36);
  const [hover, setHover] = useState(null);
  const [ref, width] = useWidth();
  const unit = report.meta.unit;

  const normals = useMemo(() => monthlyNormals(report[scope].rows), [report, scope]);
  const rows = useMemo(() => chartWindow(monthlySeries(report[scope], report.continuation?.[scope]), normals, span),
    [report, scope, span, normals]);

  const plotWidth = Math.max(0, width - PAD.left - PAD.right);
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  // Rain, runoff and snow cannot go below zero, so neither can their error band:
  // a band drawn to -8 mm would put an impossible value on the axis.
  const floor = useMemo(() => (rows.every(row => row.value >= 0) ? 0 : -Infinity), [rows]);
  const geometry = useMemo(() => {
    if (!rows.length || !plotWidth) return null;
    const values = rows.flatMap(row => [row.value, row.normal,
      row.errorP90 ? row.value + row.errorP90 : null, row.errorP90 ? Math.max(floor, row.value - row.errorP90) : null])
      .filter(value => value !== null && value !== undefined);
    let low = Math.min(...values), high = Math.max(...values);
    if (low === high) { low -= 1; high += 1; }
    const first = rows[0].key, last = rows.at(-1).key;
    const x = key => (last === first ? plotWidth / 2 : ((key - first) / (last - first)) * plotWidth);
    const y = value => plotHeight - ((value - low) / (high - low)) * plotHeight;
    return { low, high, first, last, x, y };
  }, [rows, plotWidth, plotHeight, floor]);

  if (!rows.length) return null;
  const path = run => run.map(({ row, value }, index) =>
    `${index ? 'L' : 'M'}${geometry.x(row.key).toFixed(1)},${geometry.y(value).toFixed(1)}`).join('');
  const band = run => `${run.map(({ row, value }, index) =>
    `${index ? 'L' : 'M'}${geometry.x(row.key).toFixed(1)},${geometry.y(value + row.errorP90).toFixed(1)}`).join('')}${
    [...run].reverse().map(({ row, value }) =>
      `L${geometry.x(row.key).toFixed(1)},${geometry.y(Math.max(floor, value - row.errorP90)).toFixed(1)}`).join('')}Z`;

  const observed = geometry ? runs(rows, row => (row.source === 'observed' ? row.value : null)) : [];
  const estimated = geometry ? runs(rows, row => (row.source !== 'observed' ? row.value : null)) : [];
  const normal = geometry ? runs(rows, row => row.normal) : [];
  const hasEstimate = estimated.length > 0;
  const hasNormal = normal.length > 0;

  // Year ticks thin out with the width available, so labels never collide.
  const years = geometry ? [...new Set(rows.filter(row => row.month === 1).map(row => row.year))] : [];
  const every = Math.max(1, Math.ceil(years.length / Math.max(1, Math.floor(plotWidth / 48))));
  const pick = event => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - box.left - PAD.left;
    let best = null;
    for (const row of rows) {
      const distance = Math.abs(geometry.x(row.key) - px);
      if (!best || distance < best.distance) best = { row, distance };
    }
    setHover(best?.row || null);
  };
  const active = hover && rows.includes(hover) ? hover : null;
  const anomaly = active && active.normal !== null ? active.value - active.normal : null;

  return <section className="poi-chart" aria-label="Monthly series against the normal">
    <div className="poi-chart-controls">
      {hasUpstream && <div role="group" aria-label="Area">
        {[['local', 'Local'], ['upstream', 'Upstream']].map(([id, text]) => <button key={id} type="button"
          aria-pressed={scope === id} onClick={() => { setScope(id); setHover(null); }}>{text}</button>)}
      </div>}
      <div role="group" aria-label="Period">
        {SPANS.map(([months, text]) => <button key={text} type="button" aria-pressed={span === months}
          onClick={() => { setSpan(months); setHover(null); }}>{text}</button>)}
      </div>
    </div>
    <ul className="poi-chart-legend">
      <li><i className="poi-key-observed"/>Gridded record</li>
      {hasEstimate && <li><i className="poi-key-estimated"/>Provisional estimate · p90 error band</li>}
      {hasNormal && <li><i className="poi-key-normal"/>Normal {normals.firstYear}–{normals.lastYear}</li>}
    </ul>
    <div ref={ref} className="poi-chart-frame">
      {geometry && <svg width={width} height={HEIGHT} role="img"
        aria-label={`${report.meta.label}, ${scope === 'local' ? 'local basin' : 'upstream catchment'}, ${label(rows[0])} to ${label(rows.at(-1))}`}
        onPointerMove={pick} onPointerDown={pick} onPointerLeave={event => { if (event.pointerType === 'mouse') setHover(null); }}>
        <g transform={`translate(${PAD.left} ${PAD.top})`}>
          {[geometry.high, (geometry.high + geometry.low) / 2, geometry.low].map((value, index) => {
            const y = (plotHeight / 2) * index;
            return <g key={index}>
              <line x1={0} x2={plotWidth} y1={y} y2={y} className="poi-chart-grid"/>
              <text x={-6} y={y + 4} textAnchor="end" className="poi-chart-axis">{formatNumber(value, 1)}</text>
            </g>;
          })}
          {years.filter((_, index) => index % every === 0).map(year => {
            const x = geometry.x(year * 12);
            return <text key={year} x={x} y={plotHeight + 16} textAnchor="middle" className="poi-chart-axis">{year}</text>;
          })}
          {estimated.filter(run => run.every(({ row }) => row.errorP90)).map((run, index) =>
            <path key={`b${index}`} d={band(run)} className="poi-chart-band"/>)}
          {normal.map((run, index) => <path key={`n${index}`} d={path(run)} className="poi-chart-normal"/>)}
          {observed.map((run, index) => run.length === 1
            ? <circle key={`o${index}`} cx={geometry.x(run[0].row.key)} cy={geometry.y(run[0].value)} r={2} className="poi-chart-dot"/>
            : <path key={`o${index}`} d={path(run)} className="poi-chart-observed"/>)}
          {estimated.map((run, index) => <path key={`e${index}`} d={path(run)} className="poi-chart-estimated"/>)}
          {active && <>
            <line x1={geometry.x(active.key)} x2={geometry.x(active.key)} y1={0} y2={plotHeight} className="poi-chart-cursor"/>
            <circle cx={geometry.x(active.key)} cy={geometry.y(active.value)} r={4}
              className={active.source === 'observed' ? 'poi-chart-marker' : 'poi-chart-marker estimated'}/>
          </>}
        </g>
      </svg>}
    </div>
    <p className="poi-chart-readout" aria-live="polite">{active
      ? <><strong>{label(active)}</strong> · {formatNumber(active.value, 2)} {unit}
        {active.errorP90 ? ` ±${formatNumber(active.errorP90, 2)}` : ''}
        {active.source === 'observed' ? ' · observed' : ' · estimated'}
        {anomaly !== null && ` · normal ${formatNumber(active.normal, 2)} · ${anomaly >= 0 ? '+' : ''}${formatNumber(anomaly, 2)}`}</>
      : `Touch or hover the chart to read a month · ${unit}`}</p>
  </section>;
}
