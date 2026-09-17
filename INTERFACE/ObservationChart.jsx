import React, { useState } from 'react';

/**
 * Raw per-pass satellite observations plus a LOESS-smoothed trend, with
 * flagged points (a partial-swath pass, an outlier reading) drawn distinctly
 * rather than hidden — the chart should look exactly as uneven as the record
 * actually is. Unlike the case-studies TimeSeriesChart (which places rows at
 * even index positions), points here are irregularly spaced in real time, so
 * the x-axis is a genuine time scale.
 */
export default function ObservationChart({ observations, loess, valueKey, flagKey, unit, title, color, flagLabel }) {
  const [hover, setHover] = useState(null);
  const width = 760, height = 260, left = 58, right = 22, top = 22, bottom = 40;

  const points = observations
    .filter(o => o[valueKey] != null)
    .map(o => ({ t: new Date(o.time + 'T00:00:00Z').getTime(), v: o[valueKey], flagged: !!o[flagKey], time: o.time }));
  const trend = (loess || [])
    .filter(p => p.value != null)
    .map(p => ({ t: new Date(p.time + 'T00:00:00Z').getTime(), v: p.value }));

  if (!points.length) return <p>No eligible observations for this selection.</p>;

  const good = points.filter(p => !p.flagged);
  const flagged = points.filter(p => p.flagged);

  const allT = points.map(p => p.t).concat(trend.map(p => p.t));
  const tMin = Math.min(...allT), tMax = Math.max(...allT, tMin + 1);
  // The vertical scale is set from the unflagged points and the trend line
  // only. An outlier reading is, by definition, off the real scale of the
  // record (a physically-impossible elevation is not "a bit high", see the
  // Toktogul case in the case study) — letting a handful of them stretch the
  // axis would flatten the entire real signal to a line near zero. Flagged
  // points are still drawn, clamped to the visible edge, so their existence
  // and count stay visible without hiding what the good data actually shows.
  const scaleSource = good.length ? good : points;
  const allV = scaleSource.map(p => p.v).concat(trend.map(p => p.v));
  const vMin = Math.min(0, ...allV), vMax = Math.max(...allV, vMin + 0.01) * 1.08;
  const x = t => left + (t - tMin) / (tMax - tMin) * (width - left - right);
  const y = v => top + (vMax - Math.min(Math.max(v, vMin), vMax)) / (vMax - vMin) * (height - top - bottom);
  const offScale = v => v < vMin || v > vMax;

  const trendPath = trend.map((p, i) => `${i ? 'L' : 'M'}${x(p.t)},${y(p.v)}`).join(' ');

  const yearTicks = [];
  for (let y0 = new Date(tMin).getUTCFullYear(); y0 <= new Date(tMax).getUTCFullYear() + 1; y0++) {
    const t = Date.UTC(y0, 0, 1);
    if (t >= tMin && t <= tMax) yearTicks.push({ t, label: String(y0) });
  }

  const nearest = px => {
    let best = null, bestDist = Infinity;
    for (const p of points) {
      const d = Math.abs(x(p.t) - px);
      if (d < bestDist) { bestDist = d; best = p; }
    }
    return best;
  };

  return <figure className="cs-chart">
    <figcaption>{title} <span>{unit}</span></figcaption>
    <svg viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label={`${title}, ${unit}. ${points.length} observations since ${points[0].time}, ${flagged.length} flagged. Exact values are available in the data table below.`}
      onMouseLeave={() => setHover(null)}
      onMouseMove={event => {
        const box = event.currentTarget.getBoundingClientRect();
        const px = (event.clientX - box.left) / box.width * width;
        setHover(nearest(px));
      }}>
      {[0, 1, 2, 3, 4].map(i => {
        const value = vMin + (vMax - vMin) * i / 4;
        return <g key={i}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="cs-grid" />
          <text x={left - 10} y={y(value) + 4} textAnchor="end">{value.toLocaleString('en', { maximumFractionDigits: vMax - vMin < 3 ? 2 : 0 })}</text></g>;
      })}
      {yearTicks.map(({ t, label }) => <text key={label} x={x(t)} y={height - 13} textAnchor="middle">{label}</text>)}
      {trendPath && <path d={trendPath} fill="none" stroke={color} strokeWidth="2.2" opacity="0.9" />}
      {good.map((p, i) => <circle key={`g${i}`} cx={x(p.t)} cy={y(p.v)} r="2.6" fill={color} opacity="0.55" />)}
      {flagged.map((p, i) => offScale(p.v)
        ? <path key={`f${i}`} d={`M${x(p.t) - 4},${y(p.v) + (p.v > vMax ? 5 : -5)} l4,${p.v > vMax ? -5 : 5} l4,${p.v > vMax ? 5 : -5}Z`}
            fill="none" stroke="#e0637a" strokeWidth="1.6" />
        : <circle key={`f${i}`} cx={x(p.t)} cy={y(p.v)} r="3.4" fill="none" stroke="#e0637a" strokeWidth="1.6" />)}
      {hover && <line x1={x(hover.t)} x2={x(hover.t)} y1={top} y2={height - bottom} className="cs-cursor" />}
    </svg>
    <div className="cs-legend">
      <span><i style={{ background: color, opacity: 0.55, borderRadius: '50%' }} />Observation</span>
      <span><i style={{ background: 'none', border: '1.6px solid #e0637a', borderRadius: '50%' }} />{flagLabel}</span>
      <span><i style={{ background: color }} />LOESS trend</span>
    </div>
    <div className="cs-readout">
      {hover
        ? `${hover.time} · ${hover.v.toLocaleString('en', { maximumFractionDigits: 2 })} ${unit}${hover.flagged ? ` · ${flagLabel.toLowerCase()}` : ''}`
        : `Move across the chart to inspect values. ${flagged.length} of ${points.length} observations flagged as ${flagLabel.toLowerCase()}.`}
    </div>
    <details><summary>View exact observations</summary><div className="cs-table-wrap"><table>
      <thead><tr><th>Date</th><th>{title} ({unit})</th><th>{flagLabel}</th></tr></thead>
      <tbody>{points.map((p, i) => <tr key={i}><td>{p.time}</td><td>{p.v.toLocaleString('en', { maximumFractionDigits: 3 })}</td><td>{p.flagged ? 'Yes' : ''}</td></tr>)}</tbody>
    </table></div></details>
  </figure>;
}
