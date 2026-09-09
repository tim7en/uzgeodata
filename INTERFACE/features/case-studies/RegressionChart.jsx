import React from 'react';

const finite = value => typeof value === 'number' && Number.isFinite(value);
const fmt = value => finite(value) ? value.toLocaleString('en', { maximumFractionDigits: 3 }) : 'Unavailable';

export default function RegressionChart({ rows, xKey, yKey, xLabel, yLabel, title, scores }) {
  const points = rows.filter(r => finite(r[xKey]) && finite(r[yKey]));
  if (!points.length) return <figure className="cs-chart"><figcaption>{title}</figcaption><p>No eligible paired observations.</p></figure>;
  const extent = key => {
    const values = points.map(r => r[key]);
    const min = Math.min(...values), max = Math.max(...values), pad = (max - min || 1) * .08;
    return [min - pad, max + pad];
  };
  const [xmin, xmax] = extent(xKey), [ymin, ymax] = extent(yKey);
  const x = value => 72 + (value - xmin) / (xmax - xmin) * 520;
  const y = value => 262 - (value - ymin) / (ymax - ymin) * 230;
  const line = scores && finite(scores.slope) && finite(scores.intercept);
  // Clip a fitted segment to the plotting rectangle without document-wide SVG IDs.
  let a = xmin, b = xmax;
  if (line && scores.slope !== 0) {
    const bounds = [(ymin - scores.intercept) / scores.slope, (ymax - scores.intercept) / scores.slope].sort((u,v) => u-v);
    a = Math.max(a, bounds[0]); b = Math.min(b, bounds[1]);
  }
  return <figure className="cs-chart cs-regression">
    <figcaption>{title}</figcaption>
    <svg viewBox="0 0 630 330" role="img" aria-label={`${title}. ${points.length} pairs. Exact data below.`}>
      {[0,1,2,3,4].map(i => <g key={i}>
        <line className="cs-grid" x1="72" x2="592" y1={y(ymin+(ymax-ymin)*i/4)} y2={y(ymin+(ymax-ymin)*i/4)}/>
        <text x="62" y={y(ymin+(ymax-ymin)*i/4)+4} textAnchor="end">{fmt(ymin+(ymax-ymin)*i/4)}</text>
        <text x={x(xmin+(xmax-xmin)*i/4)} y="284" textAnchor="middle">{fmt(xmin+(xmax-xmin)*i/4)}</text>
      </g>)}
      {line && a <= b && <line x1={x(a)} x2={x(b)} y1={y(scores.intercept+scores.slope*a)} y2={y(scores.intercept+scores.slope*b)} stroke="#edb06c" strokeWidth="2"/>}
      {points.map((r,i) => <circle key={i} cx={x(r[xKey])} cy={y(r[yKey])} r="4" fill="#58c9e5" opacity=".75"><title>{r.label || r.period || r.station_id}: {fmt(r[xKey])}, {fmt(r[yKey])}</title></circle>)}
      <text x="332" y="317" textAnchor="middle">{xLabel}</text>
      <text transform="translate(16 148) rotate(-90)" textAnchor="middle">{yLabel}</text>
    </svg>
    {scores && <p className="cs-note">n = {scores.n} · r = {fmt(scores.r)} · R² = {fmt(scores.r2)} · slope = {fmt(scores.slope)}
      {scores.slope_interval ? <> · 95% block-bootstrap slope interval: {scores.slope_interval.map(fmt).join(' to ')} ({scores.blocks} blocks)</> : ' · Interval unavailable (insufficient blocks or variation).'} Descriptive association, not causation.</p>}
    <details><summary>View exact paired data</summary><div className="cs-table-wrap"><table><thead><tr><th>Site / period</th><th>{xLabel}</th><th>{yLabel}</th></tr></thead><tbody>{points.map((r,i) => <tr key={i}><td>{r.label || r.period || r.station_id}</td><td>{fmt(r[xKey])}</td><td>{fmt(r[yKey])}</td></tr>)}</tbody></table></div></details>
  </figure>;
}
